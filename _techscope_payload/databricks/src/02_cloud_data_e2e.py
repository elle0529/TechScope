# Databricks notebook source
# MAGIC %md
# MAGIC # TechScope P1D — Cloud Data E2E
# MAGIC
# MAGIC Actual runtime path:
# MAGIC ADLS Bronze → Databricks Silver/Gold/RAG → Azure SQL.
# MAGIC
# MAGIC Semantic ambiguity is preserved instead of invented.

# COMMAND ----------

import json

from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

dbutils.widgets.text("storage_account", "")
dbutils.widgets.text("file_system", "techscope")
dbutils.widgets.text("secret_scope", "techscope")
dbutils.widgets.text("adls_key_secret", "adls-key")
dbutils.widgets.text("sql_server_fqdn", "")
dbutils.widgets.text("sql_database", "")
dbutils.widgets.text("sql_user_secret", "sql-user")
dbutils.widgets.text("sql_password_secret", "sql-password")

storage_account = dbutils.widgets.get("storage_account").strip()
file_system = dbutils.widgets.get("file_system").strip()
secret_scope = dbutils.widgets.get("secret_scope").strip()
adls_key_secret = dbutils.widgets.get("adls_key_secret").strip()
sql_server_fqdn = dbutils.widgets.get("sql_server_fqdn").strip()
sql_database = dbutils.widgets.get("sql_database").strip()
sql_user_secret = dbutils.widgets.get("sql_user_secret").strip()
sql_password_secret = dbutils.widgets.get("sql_password_secret").strip()

required = {
    "storage_account": storage_account,
    "file_system": file_system,
    "secret_scope": secret_scope,
    "sql_server_fqdn": sql_server_fqdn,
    "sql_database": sql_database,
}
missing = [k for k, v in required.items() if not v]
if missing:
    raise ValueError("Missing required parameters: " + ", ".join(missing))

storage_key = dbutils.secrets.get(secret_scope, adls_key_secret)
sql_user = dbutils.secrets.get(secret_scope, sql_user_secret)
sql_password = dbutils.secrets.get(secret_scope, sql_password_secret)

spark.conf.set(
    f"fs.azure.account.key.{storage_account}.dfs.core.windows.net",
    storage_key,
)

root = f"abfss://{file_system}@{storage_account}.dfs.core.windows.net"
bronze = f"{root}/bronze"
silver = f"{root}/silver"
gold = f"{root}/gold"
rag = f"{root}/rag"

SOURCE_ID = "SRC001"

# COMMAND ----------

def read_bronze(entity: str):
    return (
        spark.read
        .option("header", True)
        .option("multiLine", False)
        .option("escape", '"')
        .csv(f"{bronze}/{entity}/*/*/*/*.csv")
    )


def clean_key(col):
    return F.trim(
        F.regexp_replace(
            F.lower(F.coalesce(col, F.lit(""))),
            r"[^0-9a-zA-Z가-힣+#.]+",
            " ",
        )
    )


def stable_id(prefix: str, name_col: str):
    window = Window.orderBy(F.col(name_col))
    return F.concat(
        F.lit(prefix),
        F.lpad(F.row_number().over(window).cast("string"), 4, "0"),
    )


def write_delta(df, path: str):
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

input_partitions = raw_technology.rdd.getNumPartitions()
distribution_probe = raw_technology.repartition(4, "category_raw")
repartitioned_partitions = distribution_probe.rdd.getNumPartitions()

aliases = [
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
    ("synapse", "Azure Synapse Analytics"),
    ("azure synapse", "Azure Synapse Analytics"),
    ("ssas", "SSAS"),
    ("azure analysis services", "Azure Analysis Services"),
    ("aas", "Azure Analysis Services"),
    ("mlflow", "MLflow"),
]
alias_df = spark.createDataFrame(aliases, ["alias_key", "canonical_name"])

# COMMAND ----------

tech = (
    raw_technology
    .select(
        F.trim("technology_raw").alias("TechnologyRaw"),
        F.trim("category_raw").alias("CategoryName"),
        F.upper(F.trim("evidence_type")).alias("EvidenceType"),
        F.coalesce(F.col("source_id"), F.lit(SOURCE_ID)).alias("SourceId"),
    )
    .filter(F.length("TechnologyRaw") > 0)
    .withColumn("AliasKey", clean_key(F.col("TechnologyRaw")))
    .join(alias_df, F.col("AliasKey") == F.col("alias_key"), "left")
    .withColumn(
        "TechnologyName",
        F.coalesce(F.col("canonical_name"), F.col("TechnologyRaw")),
    )
    .dropDuplicates(["TechnologyName", "CategoryName", "EvidenceType", "SourceId"])
)

dim_technology_seed = (
    tech.select("TechnologyName")
    .dropDuplicates()
    .orderBy("TechnologyName")
)
dim_technology = (
    dim_technology_seed
    .withColumn("TechnologyId", stable_id("T", "TechnologyName"))
    .select("TechnologyId", "TechnologyName")
)

silver_technology = (
    tech
    .join(dim_technology, "TechnologyName", "left")
    .select(
        "TechnologyId",
        "TechnologyName",
        "CategoryName",
        "EvidenceType",
        "SourceId",
    )
)

category_seed = (
    raw_category
    .select(
        F.trim("category_raw").alias("CategoryName"),
        F.coalesce(F.col("source_id"), F.lit(SOURCE_ID)).alias("SourceId"),
    )
    .filter(F.length("CategoryName") > 0)
    .dropDuplicates(["CategoryName", "SourceId"])
    .orderBy("CategoryName")
)
dim_category = (
    category_seed
    .withColumn("CategoryId", stable_id("CAT", "CategoryName"))
    .select("CategoryId", "CategoryName", "SourceId")
)

# COMMAND ----------

relation_base = (
    raw_relation
    .select(
        F.trim("flow_fragment_raw").alias("FlowFragment"),
        F.coalesce(F.col("source_id"), F.lit(SOURCE_ID)).alias("SourceId"),
    )
    .filter(F.length("FlowFragment") > 0)
    .withColumn("Parts", F.split(F.col("FlowFragment"), r"\s*(?:→|->)\s*"))
)

relation_candidates = (
    relation_base
    .filter(F.size("Parts") == 2)
    .withColumn("SourceRaw", F.trim(F.element_at("Parts", 1)))
    .withColumn("TargetRaw", F.trim(F.element_at("Parts", 2)))
    .withColumn("SourceKey", clean_key(F.col("SourceRaw")))
    .withColumn("TargetKey", clean_key(F.col("TargetRaw")))
)

source_alias = alias_df.select(
    F.col("alias_key").alias("SourceAliasKey"),
    F.col("canonical_name").alias("SourceCanonical"),
)
target_alias = alias_df.select(
    F.col("alias_key").alias("TargetAliasKey"),
    F.col("canonical_name").alias("TargetCanonical"),
)

relation_named = (
    relation_candidates
    .join(source_alias, F.col("SourceKey") == F.col("SourceAliasKey"), "left")
    .join(target_alias, F.col("TargetKey") == F.col("TargetAliasKey"), "left")
    .withColumn("SourceTechnologyName", F.coalesce("SourceCanonical", "SourceRaw"))
    .withColumn("TargetTechnologyName", F.coalesce("TargetCanonical", "TargetRaw"))
)

src_dim = dim_technology.select(
    F.col("TechnologyName").alias("SourceTechnologyName"),
    F.col("TechnologyId").alias("SourceTechnologyId"),
)
dst_dim = dim_technology.select(
    F.col("TechnologyName").alias("TargetTechnologyName"),
    F.col("TechnologyId").alias("TargetTechnologyId"),
)

fact_relation = (
    relation_named
    .join(src_dim, "SourceTechnologyName", "left")
    .join(dst_dim, "TargetTechnologyName", "left")
    .withColumn("RelationType", F.lit("flows_to"))
    .withColumn("EvidenceType", F.lit("DIRECT"))
    .filter(
        F.col("SourceTechnologyId").isNotNull()
        & F.col("TargetTechnologyId").isNotNull()
    )
    .select(
        "SourceTechnologyId",
        "TargetTechnologyId",
        "RelationType",
        "EvidenceType",
        "SourceId",
    )
    .dropDuplicates()
)

unresolved_relation = (
    relation_base
    .filter(F.size("Parts") != 2)
    .select("FlowFragment", "SourceId")
    .withColumn("ResolutionStatus", F.lit("ambiguous_flow_fragment"))
)

# COMMAND ----------

architecture_rows = [
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
dim_architecture = spark.createDataFrame(
    architecture_rows,
    ["LayerCode", "LayerName"],
)

company_schema = T.StructType([
    T.StructField("CompanyId", T.StringType(), True),
    T.StructField("CompanyName", T.StringType(), True),
    T.StructField("Industry", T.StringType(), True),
    T.StructField("SourceId", T.StringType(), True),
])
dim_company = spark.createDataFrame([], company_schema)

company_technology_schema = T.StructType([
    T.StructField("CompanyId", T.StringType(), True),
    T.StructField("TechnologyId", T.StringType(), True),
    T.StructField("UseCase", T.StringType(), True),
    T.StructField("BusinessEffect", T.StringType(), True),
    T.StructField("EvidenceType", T.StringType(), True),
    T.StructField("SourceId", T.StringType(), True),
])
fact_company_technology = spark.createDataFrame([], company_technology_schema)

unresolved_company = (
    raw_company
    .select(
        "category_raw",
        "direct_cell_raw",
        "flow_cell_raw",
        "indirect_cell_raw",
        F.coalesce(F.col("source_id"), F.lit(SOURCE_ID)).alias("SourceId"),
    )
    .withColumn("ResolutionStatus", F.lit("no_dedicated_company_field"))
)

# COMMAND ----------

write_delta(silver_technology, f"{silver}/technology")
write_delta(dim_category, f"{silver}/category")
write_delta(fact_relation, f"{silver}/technology_relation")
write_delta(unresolved_relation, f"{silver}/technology_relation_unresolved")
write_delta(unresolved_company, f"{silver}/company_unresolved")

dim_technology_gold = (
    dim_technology
    .join(
        silver_technology
        .groupBy("TechnologyId", "TechnologyName")
        .agg(
            F.first("CategoryName", ignorenulls=True).alias("CategoryName"),
            F.first("SourceId", ignorenulls=True).alias("SourceId"),
        ),
        ["TechnologyId", "TechnologyName"],
        "left",
    )
)

write_delta(dim_technology_gold, f"{gold}/dim_technology")
write_delta(dim_category, f"{gold}/dim_category")
write_delta(dim_company, f"{gold}/dim_company")
write_delta(dim_architecture, f"{gold}/dim_architecture")
write_delta(fact_relation, f"{gold}/fact_technology_relation")
write_delta(fact_company_technology, f"{gold}/fact_company_technology")

technology_summary = (
    silver_technology
    .groupBy("CategoryName")
    .agg(
        F.countDistinct("TechnologyId").alias("TechnologyCount"),
        F.count("*").alias("ClaimCount"),
    )
)
write_delta(technology_summary, f"{gold}/technology_summary")

# COMMAND ----------

rag_window = Window.orderBy("TechnologyId")
rag_chunks = (
    dim_technology_gold
    .orderBy("TechnologyId")
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
            F.concat(F.lit("Technology: "), F.col("TechnologyName")),
            F.concat(F.lit("Category: "), F.coalesce(F.col("CategoryName"), F.lit("Unresolved"))),
        ),
    )
    .withColumn("technology", F.array(F.col("TechnologyName")))
    .withColumn("technology_ids", F.array(F.col("TechnologyId")))
    .withColumn(
        "category",
        F.when(F.col("CategoryName").isNotNull(), F.array(F.col("CategoryName")))
        .otherwise(F.array().cast("array<string>")),
    )
    .withColumn("architecture_layer", F.array().cast("array<string>"))
    .withColumn("evidence_type", F.lit("DIRECT"))
    .withColumn("company", F.array().cast("array<string>"))
    .withColumn("source_id", F.coalesce(F.col("SourceId"), F.lit(SOURCE_ID)))
    .select(
        "chunk_id",
        "content",
        "technology",
        "technology_ids",
        "category",
        "architecture_layer",
        "evidence_type",
        "company",
        "source_id",
    )
)

rag_tmp = f"{rag}/_knowledge_chunks_tmp"
rag_target = f"{rag}/knowledge_chunks.jsonl"

rag_chunks.coalesce(1).write.mode("overwrite").json(rag_tmp)
part_files = [x.path for x in dbutils.fs.ls(rag_tmp) if x.name.startswith("part-")]
if len(part_files) != 1:
    raise RuntimeError(f"Expected one RAG part file, got {len(part_files)}")
dbutils.fs.rm(rag_target, True)
dbutils.fs.mv(part_files[0], rag_target)
dbutils.fs.rm(rag_tmp, True)

# COMMAND ----------

jdbc_url = (
    f"jdbc:sqlserver://{sql_server_fqdn}:1433;"
    f"database={sql_database};"
    "encrypt=true;"
    "trustServerCertificate=false;"
    "hostNameInCertificate=*.database.windows.net;"
    "loginTimeout=30;"
)

jdbc_props = {
    "user": sql_user,
    "password": sql_password,
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
}

jvm = spark._sc._gateway.jvm
jvm.java.lang.Class.forName("com.microsoft.sqlserver.jdbc.SQLServerDriver")
conn = jvm.java.sql.DriverManager.getConnection(jdbc_url, sql_user, sql_password)
stmt = conn.createStatement()
stmt.execute("IF SCHEMA_ID('techscope') IS NULL EXEC('CREATE SCHEMA techscope')")
stmt.close()
conn.close()

sql_tables = [
    (dim_technology_gold, "techscope.DimTechnology"),
    (dim_category, "techscope.DimCategory"),
    (dim_company, "techscope.DimCompany"),
    (dim_architecture, "techscope.DimArchitecture"),
    (fact_relation, "techscope.FactTechnologyRelation"),
    (fact_company_technology, "techscope.FactCompanyTechnology"),
]

for frame, table in sql_tables:
    (
        frame.write
        .mode("overwrite")
        .jdbc(jdbc_url, table, properties=jdbc_props)
    )

conn = jvm.java.sql.DriverManager.getConnection(jdbc_url, sql_user, sql_password)
stmt = conn.createStatement()

stmt.execute("""
IF OBJECT_ID('techscope.FactAIInteraction','U') IS NULL
CREATE TABLE techscope.FactAIInteraction(
    InteractionId uniqueidentifier NOT NULL,
    OccurredAtUtc datetime2(3) NOT NULL,
    QuestionLength int NULL,
    RetrievedChunkCount int NULL,
    AnswerGrounded bit NULL,
    ResponseLatencyMs int NULL,
    FeedbackScore tinyint NULL,
    SourceId varchar(16) NULL
)
""")

stmt.execute("""
CREATE OR ALTER VIEW techscope.vwTechnologyOverview AS
SELECT
    t.TechnologyId,
    t.TechnologyName,
    t.CategoryName,
    t.SourceId,
    COUNT(DISTINCT r.TargetTechnologyId) AS OutgoingRelationCount,
    CAST(0 AS bigint) AS CompanyCount
FROM techscope.DimTechnology t
LEFT JOIN techscope.FactTechnologyRelation r
    ON r.SourceTechnologyId=t.TechnologyId
GROUP BY
    t.TechnologyId,
    t.TechnologyName,
    t.CategoryName,
    t.SourceId
""")

stmt.execute("""
CREATE OR ALTER VIEW techscope.vwCategorySummary AS
SELECT
    c.CategoryId,
    c.CategoryName,
    COUNT(DISTINCT t.TechnologyId) AS TechnologyCount
FROM techscope.DimCategory c
LEFT JOIN techscope.DimTechnology t
    ON t.CategoryName=c.CategoryName
GROUP BY c.CategoryId,c.CategoryName
""")

stmt.execute("""
CREATE OR ALTER VIEW techscope.vwAIInteractionSummary AS
SELECT
    CAST(OccurredAtUtc AS date) AS InteractionDate,
    COUNT_BIG(*) AS InteractionCount,
    SUM(CASE WHEN AnswerGrounded=1 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS GroundedCount,
    AVG(CONVERT(decimal(18,2),ResponseLatencyMs)) AS AvgLatencyMs,
    AVG(CONVERT(decimal(18,2),FeedbackScore)) AS AvgFeedbackScore
FROM techscope.FactAIInteraction
GROUP BY CAST(OccurredAtUtc AS date)
""")

stmt.close()
conn.close()

# COMMAND ----------

metrics = {
    "input_partitions": input_partitions,
    "repartitioned_partitions": repartitioned_partitions,
    "technology_count": dim_technology_gold.count(),
    "category_count": dim_category.count(),
    "relation_count": fact_relation.count(),
    "unresolved_relation_count": unresolved_relation.count(),
    "unresolved_company_count": unresolved_company.count(),
    "rag_chunk_count": rag_chunks.count(),
}

marker = spark.createDataFrame(
    [(json.dumps(metrics, ensure_ascii=False),)],
    ["payload"],
)
marker.coalesce(1).write.mode("overwrite").text(f"{root}/results/p1d-databricks-success")

print("TECHSCOPE_DATABRICKS_CLOUD_E2E=PASS")
print(metrics)
