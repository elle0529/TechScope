from pathlib import Path

REPAIR = Path("/workspaces/TechScope/tools/p1e_relation_repair.py")
NOTEBOOK = Path("/workspaces/TechScope/databricks/p1e_relation_repair_task.py")

repair = REPAIR.read_text(encoding="utf-8")
nb = NOTEBOOK.read_text(encoding="utf-8")

# ---------------------------------------------------------------------
# 1. Serverless job compute: omit classic compute configuration entirely.
#    Supported notebook tasks run on serverless when no classic compute
#    is attached.
# ---------------------------------------------------------------------
old_submit = '''    if compute["kind"] == "new_cluster":
        task["new_cluster"] = compute["spec"]
    else:
        task["existing_cluster_id"] = compute["cluster_id"]
'''

new_submit = '''    if compute["kind"] == "new_cluster":
        task["new_cluster"] = compute["spec"]
    elif compute["kind"] == "existing_cluster_id":
        task["existing_cluster_id"] = compute["cluster_id"]
    elif compute["kind"] == "serverless":
        # No new_cluster / existing_cluster_id: supported notebook task
        # is executed with Databricks-managed serverless compute.
        pass
    else:
        raise RuntimeError(
            "UNKNOWN_DATABRICKS_COMPUTE_KIND="
            + str(compute.get("kind"))
        )
'''

if old_submit in repair:
    repair = repair.replace(old_submit, new_submit, 1)
elif 'elif compute["kind"] == "serverless":' not in repair:
    raise RuntimeError("SUBMIT_JOB_COMPUTE_BLOCK_NOT_FOUND")

old_main = '''    compute = discover_compute()
    print(
        "DATABRICKS_COMPUTE="
        + compute["kind"]
        + " SOURCE_JOB="
        + str(compute.get("source_job_name") or "-"),
        flush=True,
    )
'''

new_main = '''    # Classic compute cannot start because the subscription currently has
    # no free Korea Central regional vCPU quota.  This workspace/region
    # supports serverless Jobs, so use Databricks-managed compute directly.
    compute = {
        "kind": "serverless",
        "source_job_id": None,
        "source_job_name": "SERVERLESS_JOB_COMPUTE",
    }
    print(
        "DATABRICKS_COMPUTE=serverless SOURCE_JOB=SERVERLESS_JOB_COMPUTE",
        flush=True,
    )
'''

if old_main in repair:
    repair = repair.replace(old_main, new_main, 1)
elif "DATABRICKS_COMPUTE=serverless SOURCE_JOB=SERVERLESS_JOB_COMPUTE" not in repair:
    raise RuntimeError("MAIN_COMPUTE_SELECTION_BLOCK_NOT_FOUND")

# Serverless should not need 15 minutes for VM allocation. Keep a generous
# ceiling but tighten the user-visible stuck threshold.
repair = repair.replace(
    "deadline = time.time() + 15 * 60",
    "deadline = time.time() + 10 * 60",
)
repair = repair.replace(
    "max_seconds=900",
    "max_seconds=600",
)

REPAIR.write_text(repair, encoding="utf-8")

# ---------------------------------------------------------------------
# 2. Serverless-safe workspace-file loading.
#    Avoid spark.read.csv(file:/Workspace/...) across executors.
# ---------------------------------------------------------------------
if "import csv" not in nb:
    nb = nb.replace(
        "import json\n",
        "import csv\nimport json\n",
        1,
    )

old_paths = '''RELATION_PATH = f"file:{BASE}/inputs/relation.csv"
TECH_PATH = f"file:{BASE}/inputs/dim_technology.csv"
ALIAS_PATH = f"file:{BASE}/inputs/technology_alias_normalized.csv"
'''

new_paths = '''RELATION_PATH = BASE / "inputs/relation.csv"
TECH_PATH = BASE / "inputs/dim_technology.csv"
ALIAS_PATH = BASE / "inputs/technology_alias_normalized.csv"
'''

if old_paths in nb:
    nb = nb.replace(old_paths, new_paths, 1)

old_reads = '''relation_df = (
    spark.read.option("header", True)
    .option("multiLine", True)
    .option("escape", '"')
    .csv(RELATION_PATH)
)

technology_df = (
    spark.read.option("header", True)
    .csv(TECH_PATH)
    .select(
        F.col("TechnologyId").alias("technology_id"),
        F.col("TechnologyName").alias("technology_name"),
    )
    .filter(F.col("technology_id").isNotNull())
    .dropDuplicates(["technology_id"])
)

alias_df = (
    spark.read.option("header", True)
    .csv(ALIAS_PATH)
    .select("alias", "canonical_name")
    .filter(F.col("alias").isNotNull() & F.col("canonical_name").isNotNull())
    .dropDuplicates(["alias", "canonical_name"])
)
'''

new_reads = '''def read_workspace_csv(path: Path):
    # Workspace files are driver-local assets.  The data set is tiny
    # (77 relation rows / 515 technologies), so read on the driver and
    # materialize a Spark DataFrame explicitly.  This avoids relying on
    # executor visibility of file:/Workspace paths on serverless compute.
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]

    if not headers:
        raise RuntimeError(f"CSV_HEADERS_EMPTY={path}")

    schema = StructType(
        [StructField(h, StringType(), True) for h in headers]
    )
    return spark.createDataFrame(rows, schema=schema)


relation_df = read_workspace_csv(RELATION_PATH)

technology_df = (
    read_workspace_csv(TECH_PATH)
    .select(
        F.col("TechnologyId").alias("technology_id"),
        F.col("TechnologyName").alias("technology_name"),
    )
    .filter(F.col("technology_id").isNotNull())
    .dropDuplicates(["technology_id"])
)

alias_df = (
    read_workspace_csv(ALIAS_PATH)
    .select("alias", "canonical_name")
    .filter(F.col("alias").isNotNull() & F.col("canonical_name").isNotNull())
    .dropDuplicates(["alias", "canonical_name"])
)
'''

if old_reads in nb:
    nb = nb.replace(old_reads, new_reads, 1)
elif "def read_workspace_csv(path: Path):" not in nb:
    raise RuntimeError("NOTEBOOK_INPUT_READ_BLOCK_NOT_FOUND")

# ---------------------------------------------------------------------
# 3. Serverless/standard-access-safe partition observation.
#    Avoid DataFrame.rdd, which is not portable to Spark Connect/serverless.
# ---------------------------------------------------------------------
old_partitions = '''partition_before = validated_df.rdd.getNumPartitions()
validated_df = validated_df.repartition(
    4, F.col("SourceTechnologyId")
)
partition_after = validated_df.rdd.getNumPartitions()

relation_count = validated_df.count()
'''

new_partitions = '''def observed_partition_count(df):
    return int(
        df.select(F.spark_partition_id().alias("_partition_id"))
        .distinct()
        .count()
    )


partition_before = observed_partition_count(validated_df)
validated_df = validated_df.repartition(
    4, F.col("SourceTechnologyId")
)
relation_count = validated_df.count()
partition_after = observed_partition_count(validated_df)
'''

if old_partitions in nb:
    nb = nb.replace(old_partitions, new_partitions, 1)
elif "def observed_partition_count(df):" not in nb:
    raise RuntimeError("NOTEBOOK_RDD_PARTITION_BLOCK_NOT_FOUND")

NOTEBOOK.write_text(nb, encoding="utf-8")

print("P1E_V5_SERVERLESS_COMPUTE_PATCH=PASS")
print("P1E_V5_WORKSPACE_FILE_PATCH=PASS")
print("P1E_V5_NO_RDD_PATCH=PASS")
