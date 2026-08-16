#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fail(msg: str) -> None:
    print("P1D_STATIC_VALIDATION=FAIL " + msg)
    raise SystemExit(1)

def main() -> int:
    required = [
        ROOT / "infra/bicep/p1-data.bicep",
        ROOT / "infra/bicep/p1-data-rg.bicep",
        ROOT / "databricks/src/02_cloud_data_e2e.py",
        ROOT / "tools/p1d_cloud_data_e2e.py",
        ROOT / "tools/p1d_sql_verify.py",
        ROOT / "tools/sync_p1d_docs.py",
    ]
    for path in required:
        if not path.exists():
            fail("missing=" + str(path.relative_to(ROOT)))

    bicep = (ROOT / "infra/bicep/p1-data-rg.bicep").read_text(encoding="utf-8-sig")
    if "name: 'standard'" in bicep:
        fail("databricks_standard_sku_retired")
    if "name: 'premium'" not in bicep:
        fail("databricks_premium_sku_missing")
    if "@concat(''bronze/''" in bicep:
        fail("bicep_adf_expression_uses_sql_style_quote_escaping")
    expected_adf_expression = r"@concat(\'bronze/\', replace(item(), \'.csv\', \'\'), \'/\', formatDateTime(utcnow(),\'yyyy/MM/dd\'))"
    if expected_adf_expression not in bicep:
        fail("bicep_adf_expression_escape_contract")
    for token in [
        "Microsoft.Storage/storageAccounts@2025-01-01",
        "Microsoft.DataFactory/factories@2018-06-01",
        "Microsoft.Databricks/workspaces@2024-05-01",
        "Microsoft.Sql/servers@2023-08-01-preview",
        "StorageV2",
        "isHnsEnabled: true",
        "authentication: 'MSI'",
        "PL_Ingest_TechScope",
        "Storage Blob Data Contributor",
    ]:
        if token == "Storage Blob Data Contributor":
            # Role is represented by the well-known role definition ID.
            if "ba92f5b4-2d11-453d-a403-e96b0029c9fe" not in bicep:
                fail("storage_role_id")
        elif token not in bicep:
            fail("bicep_token=" + token)

    notebook = (ROOT / "databricks/src/02_cloud_data_e2e.py").read_text(encoding="utf-8-sig")
    for token in [
        "repartition(4",
        "dropDuplicates",
        "TechnologyId",
        "CategoryId",
        "FactTechnologyRelation",
        "knowledge_chunks.jsonl",
        "dbutils.secrets.get",
        "jdbc:sqlserver://",
        "TECHSCOPE_DATABRICKS_CLOUD_E2E=PASS",
    ]:
        if token not in notebook:
            fail("notebook_token=" + token)

    orchestrator = (ROOT / "tools/p1d_cloud_data_e2e.py").read_text(encoding="utf-8-sig")
    for token in [
        "P1D_STAGE_GATE=PASS",
        "deployment sub",
        "pipeline-run",
        "jobs",
        "P1D_EXPECTED_TIME=15-40_MINUTES",
        "SECRETS_WRITTEN_TO_REPO=NO",
    ]:
        if token == "deployment sub":
            if '"deployment", "sub"' not in orchestrator:
                fail("orchestrator_deployment")
        elif token == "pipeline-run":
            if '"pipeline-run"' not in orchestrator:
                fail("orchestrator_adf")
        elif token == "jobs":
            if '"jobs", "submit"' not in orchestrator:
                fail("orchestrator_databricks")
        elif token not in orchestrator:
            fail("orchestrator_token=" + token)

    # P1A/P1B/P1C upstream contracts.
    upstream = [
        ROOT / "extractor/output/manifest.json",
        ROOT / "adf/PL_Ingest_TechScope.json",
        ROOT / "databricks/src/01_build_techscope.py",
        ROOT / "sql/00_schema.sql",
    ]
    for path in upstream:
        if not path.exists():
            fail("upstream_missing=" + str(path.relative_to(ROOT)))

    print("P1D_BICEP_CONTRACT=PASS")
    print("P1D_DATABRICKS_RUNTIME_CONTRACT=PASS")
    print("P1D_STAGE_SCOPED_GATE_CONTRACT=PASS")
    print("P1A_P1B_P1C_UPSTREAM_CONTRACT=PASS")
    print("P1D_STATIC_VALIDATION=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
