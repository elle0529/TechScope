#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FILES = [
    "technology.csv",
    "category.csv",
    "relation.csv",
    "company_usecase.csv",
    "architecture_mapping.csv",
]

def fail(msg: str) -> None:
    print(f"P1B_ARTIFACT_VALIDATION=FAIL {msg}")
    raise SystemExit(1)

def main() -> int:
    pipeline_path = ROOT / "adf" / "PL_Ingest_TechScope.json"
    linked_path = ROOT / "adf" / "linkedService" / "LS_ADLS_TechScope.json"
    landing_path = ROOT / "adf" / "dataset" / "DS_CSV_Landing.json"
    bronze_path = ROOT / "adf" / "dataset" / "DS_CSV_Bronze.json"
    notebook_path = ROOT / "databricks" / "src" / "01_build_techscope.py"
    bundle_path = ROOT / "databricks" / "databricks.yml"
    job_path = ROOT / "databricks" / "resources" / "techscope_job.yml"

    for path in [pipeline_path, linked_path, landing_path, bronze_path, notebook_path, bundle_path, job_path]:
        if not path.exists():
            fail(f"missing={path.relative_to(ROOT)}")

    for path in [pipeline_path, linked_path, landing_path, bronze_path]:
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            fail(f"invalid_json={path.relative_to(ROOT)} error={exc}")

    ls = json.loads(linked_path.read_text(encoding="utf-8-sig"))
    if ls["name"] != "LS_ADLS_TechScope":
        fail("linked_service_name")
    props = ls["properties"]
    if props.get("type") != "AzureBlobFS":
        fail("linked_service_type")
    if props.get("typeProperties", {}).get("authentication") != "MSI":
        fail("linked_service_auth_not_msi")

    for ds_path, expected_name in [
        (landing_path, "DS_CSV_Landing"),
        (bronze_path, "DS_CSV_Bronze"),
    ]:
        ds = json.loads(ds_path.read_text(encoding="utf-8-sig"))
        if ds["name"] != expected_name:
            fail(f"dataset_name={expected_name}")
        params = ds["properties"].get("parameters", {})
        if set(params) != {"folder_name", "file_name"}:
            fail(f"dataset_parameters={expected_name}")
        if ds["properties"].get("type") != "DelimitedText":
            fail(f"dataset_type={expected_name}")

    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8-sig"))
    if pipeline["name"] != "PL_Ingest_TechScope":
        fail("pipeline_name")

    defaults = pipeline["properties"]["parameters"]["file_list"]["defaultValue"]
    if defaults != EXPECTED_FILES:
        fail(f"file_list={defaults}")

    activities = pipeline["properties"]["activities"]
    if [a["type"] for a in activities] != ["GetMetadata", "ForEach"]:
        fail("top_level_activity_order")

    metadata = activities[0]
    foreach = activities[1]
    deps = foreach.get("dependsOn", [])
    if not deps or deps[0].get("activity") != metadata["name"]:
        fail("foreach_dependency")

    nested = foreach["typeProperties"].get("activities", [])
    if len(nested) != 1 or nested[0].get("type") != "Copy":
        fail("foreach_copy_activity")

    copy_activity = nested[0]
    output_params = copy_activity["outputs"][0]["parameters"]
    folder_expr = output_params["folder_name"]["value"]
    if "bronze/" not in folder_expr or "yyyy/MM/dd" not in folder_expr:
        fail("bronze_date_partition_expression")

    notebook = notebook_path.read_text(encoding="utf-8-sig")
    required_tokens = [
        "spark.read",
        ".dropDuplicates(",
        ".join(",
        ".groupBy(",
        ".repartition(",
        'format("delta")',
        "technology_id",
        "category_id",
        "fact_technology_relation",
        "knowledge_chunks.jsonl",
        "unresolved",
        "CH",
    ]
    missing = [token for token in required_tokens if token not in notebook]
    if missing:
        fail(f"notebook_required_tokens={missing}")

    bundle = bundle_path.read_text(encoding="utf-8-sig")
    job = job_path.read_text(encoding="utf-8-sig")
    for token in ["bundle:", "include:", "targets:", "existing_cluster_id"]:
        if token not in bundle:
            fail(f"bundle_token={token}")
    for token in ["resources:", "jobs:", "notebook_task:", "existing_cluster_id:"]:
        if token not in job:
            fail(f"job_token={token}")

    # P1A outputs must remain available as the local upstream artifact contract.
    manifest_path = ROOT / "extractor" / "output" / "manifest.json"
    if not manifest_path.exists():
        fail("p1a_manifest_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    for name in EXPECTED_FILES:
        item = manifest.get("outputs", {}).get(name)
        if not item:
            fail(f"p1a_output_missing={name}")
        if not (ROOT / item["path"]).exists():
            fail(f"p1a_output_file_missing={name}")

    print("ADF_ARTIFACT_CONTRACT=PASS")
    print("DATABRICKS_ARTIFACT_CONTRACT=PASS")
    print("P1A_UPSTREAM_CONTRACT=PASS")
    print("P1B_ARTIFACT_VALIDATION=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
