# Databricks notebook source
# MAGIC %md
# MAGIC # TechScope — Bronze → Silver → Gold → RAG
# MAGIC
# MAGIC Baseline boundary:
# MAGIC - Databricks owns normalization, Domain ID resolution, relationship resolution,
# MAGIC   joins, aggregation, Silver/Gold curation, and RAG dataset generation.
# MAGIC - Unresolvable semantic values are retained separately instead of guessed.

# COMMAND ----------

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

dbutils.widgets.text("bronze_base", "")
dbutils.widgets.text("silver_base", "")
dbutils.widgets.text("gold_base", "")
dbutils.widgets.text("rag_base", "")

BRONZE_BASE = dbutils.widgets.get("bronze_base").rstrip("/")
SILVER_BASE = dbutils.widgets.get("silver_base").rstrip("/")
GOLD_BASE = dbutils.widgets.get("gold_base").rstrip("/")
RAG_BASE = dbutils.widgets.get("rag_base").rstrip("/")

for name, value in {
    "bronze_base": BRONZE_BASE,
    "silver_base": SILVER_BASE,
    "gold_base": GOLD_BASE,
    "rag_base": RAG_BASE,
}.items():
    if not value:
        raise ValueError(f"Required parameter is empty: {name}")

SOURCE_ID = "SRC001"

# COMMAND ----------

ALIASES = [
    ("adf", "Azure Data Factory"),
    ("azure data factory", "Azure Data Factory"),
    ("adls", "Azure Data Lake Storage Gen2"),
    ("adls gen2", "Azure Data Lake Storage Gen2"),
    ("azure data lake gen2", "Azure Data Lake Storage Gen2"),
    ("azure data lake storage gen2", "Azure Data Lake Storage Gen2"),
    ("databricks", "Azure Databricks"),
    ("azure databricks", "Azure Databricks"),
    ("powerbi", "Power BI"),
    ("power bi", "Power BI"),
    ("microsoft power bi", "Power BI"),
    ("azure sql", "Azure SQL"),
    ("azure sql database", "Azure SQL"),
    ("azure ai search", "Azure AI Search"),
    ("cognitive search", "Azure AI Search"),
    ("azure openai", "Azure OpenAI"),
    ("openai", "Azure OpenAI"),
    ("fastapi", "FastAPI"),
    ("cosmos db", "Cosmos DB"),
    ("azure cosmos db", "Cosmos DB"),
    ("teams", "Microsoft Teams"),
    ("microsoft teams", "Microsoft Teams"),
    ("ssis", "SSIS"),
    ("sql server integration services", "SSIS"),
    ("synapse", "Azure Synapse Analytics"),
    ("azure synapse", "Azure Synapse Analytics"),
    ("ssas", "SSAS"),
    ("sql server analysis services", "SSAS"),
    ("azure analysis services", "Azure Analysis Services"),
    ("aas", "Azure Analysis Services"),
    ("mlflow", "MLflow"),
]

ARCHITECTURE_LAYERS = [
    ("01", "Source"),
    ("02", "Integration"),
    ("03", "Storage"),
    ("04", "Processing"),
    ("05", "Analytics"),
    ("06", "Semantic"),
    ("07", "BI"),
    ("08", "AI"),
    ("09", "Application"),
    ("10", "Operations"),
    ("11", "Education"),
]

LAYER_RULES = [
    ("Azure Data Factory", "02", "Integration"),
    ("SSIS", "02", "Integration"),
    ("Azure Data Lake Storage Gen2", "03", "Storage"),
    ("Cosmos DB", "03", "Storage"),
    ("Azure Databricks", "04", "Processing"),
    ("Azure Synapse Analytics", "05", "Analytics"),
    ("Azure SQL", "05", "Analytics"),
    ("SSAS", "06", "Semantic"),
    ("Azure Analysis Services", "06", "Semantic"),
    ("Power BI", "07", "BI"),
    ("Azure AI Search", "08", "AI"),
    ("Azure OpenAI", "08", "AI"),
    ("FastAPI", "09", "Application"),
    ("Microsoft Teams", "09", "Application"),
    ("MLflow", "10", "Operations"),
]

alias_df = spark.createDataFrame(ALIASES, ["alias_key", "canonical_name"])
layer_df = spark.createDataFrame(LAYER_RULES, ["canonical_name", "layer_code", "layer_name"])
dim_architecture = spark.createDataFrame(ARCHITECTURE_LAYERS, ["layer_code", "layer_name"])

# COMMAND ----------

def read_bronze(entity: str) -> DataFrame:
    path = f"{BRONZE_BASE}/{entity}/*/*/*/*.csv"
    return (
        spark.read
        .option("header", True)
        .option("multiLine", False)
        .option("escape", '"')
        .csv(path)
    )


def normalized_key(column: F.Column) -> F.Column:
    return F.trim(
        F.regexp_replace(
            F.lower(F.coalesce(column, F.lit(""))),
            r"[^0-9a-zA-Z가-힣+#.]+",
            " ",
        )
    )


def stable_domain_id(prefix: str, order_col: str) -> F.Column:
    w = Window.orderBy(F.col(order_col))
    return F.concat(
        F.lit(prefix),
        F.lpad(F.row_number().over(w).cast("string"), 4, "0"),
    )


def write_delta(df: DataFrame, path: str) -> None:
    (
        df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(path)
    )

# COMMAND ----------

raw_technology = read_bronze("technology")
raw_category = read_bronze("category")
raw_relation = read_bronze("relation")
raw_company = read_bronze("company_usecase")
raw_architecture = read_bronze("architecture_mapping")

input_partition_count = raw_technology.rdd.getNumPartitions()
distribution_probe = raw_technology.repartition(4, "category_raw")
repartitioned_count = distribution_probe.rdd.getNumPartitions()

# COMMAND ----------

# Technology normalization and T* resolution.
tech_base = (
    raw_technology
    .select(
        F.trim("technology_raw").alias("technology_raw"),
        F.trim("category_raw").alias("category_raw"),
        F.upper(F.trim("evidence_type")).alias("evidence_type"),
        F.col("source_id"),
        F.col("source_row_number"),
        F.col("source_line_number"),
        F.col("source_row_sha256"),
    )
    .filter(F.length("technology_raw") > 0)
    .withColumn("technology_key_normalized", normalized_key(F.col("technology_raw")))
    .dropDuplicates(["technology_key_normalized", "category_raw", "evidence_type", "source_id"])
)

tech_resolved = (
    tech_base
    .join(
        alias_df,
        tech_base.technology_key_normalized == alias_df.alias_key,
        "left",
    )
    .withColumn(
        "technology_name",
        F.coalesce(F.col("canonical_name"), F.trim(F.col("technology_raw"))),
    )
    .withColumn(
        "resolution_status",
        F.when(F.col("canonical_name").isNotNull(), F.lit("alias_resolved"))
         .otherwise(F.lit("normalized_raw")),
    )
)

silver_technology = (
    tech_resolved
    .select(
        "technology_name",
        "category_raw",
        "evidence_type",
        "source_id",
        "resolution_status",
    )
    .dropDuplicates(["technology_name", "category_raw", "evidence_type", "source_id"])
)

technology_dim_seed = (
    silver_technology
    .select("technology_name")
    .dropDuplicates()
    .orderBy("technology_name")
)
technology_dim = (
    technology_dim_seed
    .withColumn("technology_id", stable_domain_id("T", "technology_name"))
    .select("technology_id", "technology_name")
)

silver_technology = silver_technology.join(technology_dim, "technology_name", "left")

# COMMAND ----------

# Category normalization and CAT* resolution.
silver_category = (
    raw_category
    .select(
        F.trim("category_raw").alias("category_name"),
        F.col("source_id"),
    )
    .filter(F.length("category_name") > 0)
    .dropDuplicates(["category_name", "source_id"])
    .orderBy("category_name")
    .withColumn("category_id", stable_domain_id("CAT", "category_name"))
    .select("category_id", "category_name", "source_id")
)

# COMMAND ----------

# Relationship resolution:
# Only flow fragments with exactly one explicit arrow are resolved.
# More complex/ambiguous fragments stay in the unresolved dataset.
relation_clean = (
    raw_relation
    .select(
        F.trim("flow_fragment_raw").alias("flow_fragment_raw"),
        F.trim("category_raw").alias("category_raw"),
        F.col("source_id"),
        F.col("source_row_number"),
        F.col("source_line_number"),
        F.col("source_row_sha256"),
    )
    .filter(F.length("flow_fragment_raw") > 0)
    .withColumn(
        "arrow_parts",
        F.split(F.col("flow_fragment_raw"), r"\s*(?:→|->)\s*"),
    )
)

relation_candidates = (
    relation_clean
    .filter(F.size("arrow_parts") == 2)
    .withColumn("source_technology_raw", F.trim(F.element_at("arrow_parts", 1)))
    .withColumn("target_technology_raw", F.trim(F.element_at("arrow_parts", 2)))
    .withColumn("source_key_normalized", normalized_key(F.col("source_technology_raw")))
    .withColumn("target_key_normalized", normalized_key(F.col("target_technology_raw")))
)

source_alias = alias_df.select(
    F.col("alias_key").alias("source_alias_key"),
    F.col("canonical_name").alias("source_canonical_name"),
)
target_alias = alias_df.select(
    F.col("alias_key").alias("target_alias_key"),
    F.col("canonical_name").alias("target_canonical_name"),
)

relation_named = (
    relation_candidates
    .join(
        source_alias,
        relation_candidates.source_key_normalized == source_alias.source_alias_key,
        "left",
    )
    .join(
        target_alias,
        relation_candidates.target_key_normalized == target_alias.target_alias_key,
        "left",
    )
    .withColumn(
        "source_technology_name",
        F.coalesce("source_canonical_name", "source_technology_raw"),
    )
    .withColumn(
        "target_technology_name",
        F.coalesce("target_canonical_name", "target_technology_raw"),
    )
)

source_dim = technology_dim.select(
    F.col("technology_name").alias("source_technology_name"),
    F.col("technology_id").alias("source_technology_id"),
)
target_dim = technology_dim.select(
    F.col("technology_name").alias("target_technology_name"),
    F.col("technology_id").alias("target_technology_id"),
)

silver_relation = (
    relation_named
    .join(source_dim, "source_technology_name", "left")
    .join(target_dim, "target_technology_name", "left")
    .withColumn("relation_type", F.lit("flows_to"))
    .withColumn("evidence_type", F.lit("DIRECT"))
    .withColumn(
        "resolution_status",
        F.when(
            F.col("source_technology_id").isNotNull()
            & F.col("target_technology_id").isNotNull(),
            F.lit("resolved"),
        ).otherwise(F.lit("unresolved_technology")),
    )
    .select(
        "source_technology_id",
        "source_technology_name",
        "target_technology_id",
        "target_technology_name",
        "relation_type",
        "evidence_type",
        "category_raw",
        "source_id",
        "source_row_number",
        "source_line_number",
        "source_row_sha256",
        "resolution_status",
    )
)

silver_relation_unresolved = (
    relation_clean
    .filter(F.size("arrow_parts") != 2)
    .drop("arrow_parts")
    .withColumn("resolution_status", F.lit("ambiguous_flow_fragment"))
)

# COMMAND ----------

# Company/use-case source has no dedicated canonical company column in the current
# structural extractor output. Preserve it without inventing COM* identities.
silver_company_unresolved = (
    raw_company
    .select(
        "category_raw",
        "direct_cell_raw",
        "flow_cell_raw",
        "indirect_cell_raw",
        "source_id",
        "source_row_number",
        "source_line_number",
        "source_row_sha256",
    )
    .withColumn("resolution_status", F.lit("no_dedicated_company_field"))
)

company_schema = T.StructType([
    T.StructField("company_id", T.StringType(), True),
    T.StructField("company_name", T.StringType(), True),
    T.StructField("industry", T.StringType(), True),
    T.StructField("technology_id", T.StringType(), True),
    T.StructField("use_case", T.StringType(), True),
    T.StructField("business_effect", T.StringType(), True),
    T.StructField("evidence_type", T.StringType(), True),
    T.StructField("source_id", T.StringType(), True),
])
silver_company_technology = spark.createDataFrame([], company_schema)

# COMMAND ----------

# Explicit architecture mapping only for configured canonical technologies.
silver_architecture_mapping = (
    technology_dim.alias("t")
    .join(
        layer_df.alias("l"),
        F.col("t.technology_name") == F.col("l.canonical_name"),
        "left",
    )
    .select(
        F.col("t.technology_id"),
        F.col("t.technology_name"),
        F.col("l.layer_code"),
        F.col("l.layer_name"),
        F.when(F.col("l.layer_code").isNotNull(), F.lit("resolved_rule"))
         .otherwise(F.lit("unresolved"))
         .alias("resolution_status"),
    )
)

# COMMAND ----------

# Write Silver.
write_delta(silver_technology, f"{SILVER_BASE}/technology")
write_delta(silver_category, f"{SILVER_BASE}/category")
write_delta(silver_relation, f"{SILVER_BASE}/technology_relation")
write_delta(silver_relation_unresolved, f"{SILVER_BASE}/technology_relation_unresolved")
write_delta(silver_company_technology, f"{SILVER_BASE}/company_technology")
write_delta(silver_company_unresolved, f"{SILVER_BASE}/company_unresolved")
write_delta(silver_architecture_mapping, f"{SILVER_BASE}/architecture_mapping")

# COMMAND ----------

# Gold dimensions/facts.
dim_technology = (
    technology_dim
    .join(
        silver_technology.groupBy("technology_id", "technology_name")
        .agg(
            F.first("category_raw", ignorenulls=True).alias("category_name"),
            F.first("source_id", ignorenulls=True).alias("source_id"),
        ),
        ["technology_id", "technology_name"],
        "left",
    )
)

dim_category = silver_category.select(
    "category_id", "category_name", "source_id"
)

dim_company = spark.createDataFrame(
    [],
    T.StructType([
        T.StructField("company_id", T.StringType(), True),
        T.StructField("company_name", T.StringType(), True),
        T.StructField("industry", T.StringType(), True),
    ]),
)

fact_technology_relation = (
    silver_relation
    .filter(F.col("resolution_status") == "resolved")
    .select(
        "source_technology_id",
        "target_technology_id",
        "relation_type",
        "evidence_type",
        "source_id",
    )
    .dropDuplicates()
)

fact_company_technology = silver_company_technology

technology_summary = (
    silver_technology
    .groupBy("category_raw")
    .agg(
        F.countDistinct("technology_id").alias("technology_count"),
        F.count("*").alias("claim_count"),
    )
    .orderBy(F.desc("technology_count"), "category_raw")
)

write_delta(dim_technology, f"{GOLD_BASE}/dim_technology")
write_delta(dim_category, f"{GOLD_BASE}/dim_category")
write_delta(dim_company, f"{GOLD_BASE}/dim_company")
write_delta(dim_architecture, f"{GOLD_BASE}/dim_architecture")
write_delta(fact_technology_relation, f"{GOLD_BASE}/fact_technology_relation")
write_delta(fact_company_technology, f"{GOLD_BASE}/fact_company_technology")
write_delta(technology_summary, f"{GOLD_BASE}/technology_summary")

# COMMAND ----------

# RAG dataset is generated from curated Silver/Gold material rather than raw Markdown.
rag_base = (
    dim_technology.alias("t")
    .join(
        silver_architecture_mapping.alias("a"),
        "technology_id",
        "left",
    )
    .select(
        "technology_id",
        "technology_name",
        "category_name",
        "layer_code",
        "layer_name",
        "source_id",
    )
    .dropDuplicates(["technology_id"])
    .orderBy("technology_id")
)

rag_window = Window.orderBy("technology_id")
rag_chunks = (
    rag_base
    .withColumn(
        "chunk_id",
        F.concat(
            F.lit("CH"),
            F.lpad(F.row_number().over(rag_window).cast("string"), 4, "0"),
        ),
    )
    .withColumn(
        "content",
        F.concat_ws(
            " | ",
            F.concat(F.lit("Technology: "), F.col("technology_name")),
            F.concat(F.lit("Category: "), F.coalesce(F.col("category_name"), F.lit("Unresolved"))),
            F.concat(F.lit("Architecture: "), F.coalesce(F.col("layer_name"), F.lit("Unresolved"))),
        ),
    )
    .withColumn("technology", F.array(F.col("technology_name")))
    .withColumn(
        "category",
        F.when(F.col("category_name").isNotNull(), F.array("category_name"))
         .otherwise(F.array().cast("array<string>")),
    )
    .withColumn(
        "architecture_layer",
        F.when(F.col("layer_name").isNotNull(), F.array("layer_name"))
         .otherwise(F.array().cast("array<string>")),
    )
    .withColumn("evidence_type", F.lit("DIRECT"))
    .withColumn("company", F.array().cast("array<string>"))
    .select(
        "chunk_id",
        "content",
        "technology",
        "category",
        "architecture_layer",
        "evidence_type",
        "company",
        "source_id",
    )
)

rag_tmp = f"{RAG_BASE}/_knowledge_chunks_tmp"
rag_target = f"{RAG_BASE}/knowledge_chunks.jsonl"

(
    rag_chunks.coalesce(1)
    .write.mode("overwrite")
    .json(rag_tmp)
)

part_files = [f.path for f in dbutils.fs.ls(rag_tmp) if f.name.startswith("part-")]
if len(part_files) != 1:
    raise RuntimeError(f"Expected one JSONL part file, got {len(part_files)}")

dbutils.fs.rm(rag_target, True)
dbutils.fs.mv(part_files[0], rag_target)
dbutils.fs.rm(rag_tmp, True)

# COMMAND ----------

metrics = {
    "input_partition_count": input_partition_count,
    "repartitioned_count": repartitioned_count,
    "silver_technology_count": silver_technology.count(),
    "silver_category_count": silver_category.count(),
    "resolved_relation_count": fact_technology_relation.count(),
    "unresolved_relation_count": silver_relation_unresolved.count(),
    "unresolved_company_row_count": silver_company_unresolved.count(),
    "rag_chunk_count": rag_chunks.count(),
}

print("TECHSCOPE_DATABRICKS_BUILD=PASS")
print(metrics)
