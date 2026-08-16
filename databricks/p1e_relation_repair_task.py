# Databricks notebook source
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from pyspark.sql import Row
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    StringType,
    StructField,
    StructType,
)

BASE = Path("/Workspace/Shared/TechScope/P1E_Relation_Repair")
RELATION_PATH = BASE / "inputs/relation.csv"
TECH_PATH = BASE / "inputs/dim_technology.csv"
ALIAS_PATH = BASE / "inputs/technology_alias_normalized.csv"

# -------------------------------------------------------------------------
# Read all three inputs with Spark.  The raw relation file is intentionally
# structural; final ID resolution is performed here in Databricks.
# -------------------------------------------------------------------------
def read_workspace_csv(path: Path):
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

raw_rows = relation_df.count()
tech_rows = technology_df.count()
alias_rows = alias_df.count()

tech_records = [
    (r["technology_id"], r["technology_name"])
    for r in technology_df.collect()
]
name_to_id = {name: tid for tid, name in tech_records}

alias_records = [
    (r["alias"], r["canonical_name"])
    for r in alias_df.collect()
]

# Canonical names themselves are valid resolvers; aliases only map to names
# already present in the canonical dimension.
terms = []
for tid, name in tech_records:
    n = (name or "").strip()
    if len(n) >= 3:
        terms.append((n, tid, n))

for alias, canonical in alias_records:
    a = (alias or "").strip()
    c = (canonical or "").strip()
    tid = name_to_id.get(c)
    if tid and len(a) >= 2:
        terms.append((a, tid, c))

# Longest first prevents "Power BI" from being shadowed by shorter aliases.
terms = sorted(
    {(t.lower(), tid, canonical) for t, tid, canonical in terms},
    key=lambda x: (-len(x[0]), x[0]),
)

ARROW_RE = re.compile(r"\s*(?:→|->|⇒|➜|⟶|=>|—>)\s*")
BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = BR_RE.sub(" ", value)
    value = value.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def mentions(segment: str):
    low = segment.lower()
    hits = []
    occupied = []
    for term, tid, canonical in terms:
        start = 0
        while True:
            idx = low.find(term, start)
            if idx < 0:
                break
            end = idx + len(term)
            overlap = any(not (end <= a or idx >= b) for a, b in occupied)
            if not overlap:
                occupied.append((idx, end))
                hits.append((idx, tid, canonical))
            start = idx + max(1, len(term))
    hits.sort(key=lambda x: x[0])
    out = []
    seen = set()
    for _, tid, canonical in hits:
        if tid not in seen:
            out.append((tid, canonical))
            seen.add(tid)
    return out


def resolve_raw(row):
    flow = normalize_text(row["flow_fragment_raw"])
    source_id = (row["source_id"] or "").strip()
    extract_record_id = (row["extract_record_id"] or "").strip()

    if not flow:
        return {
            "resolved": [],
            "unresolved_reason": "EMPTY_FLOW",
            "extract_record_id": extract_record_id,
            "flow": flow,
        }

    parts = [p.strip() for p in ARROW_RE.split(flow) if p.strip()]
    if len(parts) < 2:
        return {
            "resolved": [],
            "unresolved_reason": "NO_EXPLICIT_DIRECTION",
            "extract_record_id": extract_record_id,
            "flow": flow,
        }

    part_mentions = [mentions(p) for p in parts]
    resolved = []

    for i in range(len(parts) - 1):
        left = part_mentions[i]
        right = part_mentions[i + 1]
        if not left or not right:
            continue

        # A stage can explicitly contain multiple technologies.  Cross-product
        # between adjacent arrow-delimited stages preserves the source flow
        # while avoiding relation invention across non-adjacent stages.
        for src_id, src_name in left:
            for dst_id, dst_name in right:
                if src_id == dst_id:
                    continue
                resolved.append(
                    {
                        "SourceTechnologyId": src_id,
                        "TargetTechnologyId": dst_id,
                        "RelationType": "flows_to",
                        # The relation is present in the source's explicit Flow
                        # expression; therefore this is DIRECT domain evidence.
                        "EvidenceType": "DIRECT",
                        "SourceId": source_id,
                        "extract_record_id": extract_record_id,
                    }
                )

    if not resolved:
        reason = "NO_ADJACENT_TECHNOLOGY_PAIR"
    else:
        reason = None

    return {
        "resolved": resolved,
        "unresolved_reason": reason,
        "extract_record_id": extract_record_id,
        "flow": flow,
    }


needed = [
    "extract_record_id",
    "source_id",
    "flow_fragment_raw",
]
missing = [c for c in needed if c not in relation_df.columns]
if missing:
    raise RuntimeError(f"RELATION_SCHEMA_MISSING={missing}")

raw_records = relation_df.select(*needed).collect()
driver_results = [resolve_raw(r.asDict()) for r in raw_records]

resolved_rows = []
unresolved = []
resolved_fragments = 0

for item in driver_results:
    if item["resolved"]:
        resolved_fragments += 1
        resolved_rows.extend(item["resolved"])
    else:
        unresolved.append(
            {
                "extract_record_id": item["extract_record_id"],
                "reason": item["unresolved_reason"],
                "flow": item["flow"][:500],
            }
        )

schema = StructType(
    [
        StructField("SourceTechnologyId", StringType(), False),
        StructField("TargetTechnologyId", StringType(), False),
        StructField("RelationType", StringType(), False),
        StructField("EvidenceType", StringType(), False),
        StructField("SourceId", StringType(), False),
        StructField("extract_record_id", StringType(), True),
    ]
)

if resolved_rows:
    candidate_df = spark.createDataFrame(
        [Row(**r) for r in resolved_rows],
        schema=schema,
    )
else:
    candidate_df = spark.createDataFrame([], schema=schema)

# Required Spark operations: filter, dropDuplicates, join, groupBy/agg,
# repartition.  These are not cosmetic: the joins are the authoritative
# validation against DimTechnology.
candidate_df = (
    candidate_df
    .filter(
        F.col("SourceTechnologyId").isNotNull()
        & F.col("TargetTechnologyId").isNotNull()
        & (F.col("SourceTechnologyId") != F.col("TargetTechnologyId"))
    )
    .dropDuplicates(
        [
            "SourceTechnologyId",
            "TargetTechnologyId",
            "RelationType",
            "EvidenceType",
            "SourceId",
        ]
    )
)

src_dim = technology_df.select(
    F.col("technology_id").alias("SourceTechnologyId")
)
dst_dim = technology_df.select(
    F.col("technology_id").alias("TargetTechnologyId")
)

validated_df = (
    candidate_df
    .join(src_dim, "SourceTechnologyId", "inner")
    .join(dst_dim, "TargetTechnologyId", "inner")
    .select(
        "SourceTechnologyId",
        "TargetTechnologyId",
        "RelationType",
        "EvidenceType",
        "SourceId",
    )
    .dropDuplicates()
)

def observed_partition_count(df):
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

agg_rows = (
    validated_df.groupBy("RelationType", "EvidenceType")
    .agg(F.count("*").alias("relation_count"))
    .collect()
)
aggregates = [
    {
        "relation_type": r["RelationType"],
        "evidence_type": r["EvidenceType"],
        "relation_count": int(r["relation_count"]),
    }
    for r in agg_rows
]

validated_rows = [
    {
        "SourceTechnologyId": r["SourceTechnologyId"],
        "TargetTechnologyId": r["TargetTechnologyId"],
        "RelationType": r["RelationType"],
        "EvidenceType": r["EvidenceType"],
        "SourceId": r["SourceId"],
    }
    for r in validated_df.orderBy(
        "SourceTechnologyId",
        "TargetTechnologyId",
        "RelationType",
        "SourceId",
    ).collect()
]

if relation_count <= 0:
    raise RuntimeError(
        "NO_VALIDATED_RELATIONS: no explicit arrow-delimited technology "
        "relation could be resolved; SQL load must not occur"
    )

payload = {
    "status": "PASS",
    "raw_relation_rows": int(raw_rows),
    "dim_technology_rows": int(tech_rows),
    "alias_rows": int(alias_rows),
    "resolved_fragments": int(resolved_fragments),
    "unresolved_fragments": int(len(unresolved)),
    "validated_relation_rows": int(relation_count),
    "partition_before": int(partition_before),
    "partition_after": int(partition_after),
    "aggregates": aggregates,
    "relations": validated_rows,
    "unresolved_sample": unresolved[:20],
}

print("P1E_DATABRICKS_RELATION_RESOLUTION=PASS")
print(f"RAW_RELATION_ROWS={raw_rows}")
print(f"RESOLVED_FRAGMENTS={resolved_fragments}")
print(f"UNRESOLVED_FRAGMENTS={len(unresolved)}")
print(f"VALIDATED_RELATION_ROWS={relation_count}")
print(f"SPARK_PARTITIONS={partition_before}->{partition_after}")

dbutils.notebook.exit(json.dumps(payload, ensure_ascii=False))
