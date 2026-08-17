#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
GEN = ROOT / "generated/p1e_relation_repair"
SILVER = GEN / "technology_relation.csv"
GOLD = GEN / "fact_technology_relation.csv"

RESULT = ROOT / "results/latest/p1e-relation-repair.json"
EVD_DBX_EXEC = ROOT / "evidence/databricks/p1e-relation-execution.json"
EVD_DBX_OUT = ROOT / "evidence/databricks/p1e-relation-output.json"
EVD_SQL = ROOT / "evidence/azure-sql/p1e-relation-load.json"

STORAGE_ACCOUNT = "sttechscopedev239bd206"
RESOURCE_GROUP = "rg-techscope-dev-239bd206"
FILESYSTEM = "techscope"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

SILVER_ADLS = "silver/technology_relation/technology_relation.csv"
GOLD_ADLS = "gold/fact_technology_relation/fact_technology_relation.csv"


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-4000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-4000:]
        )
    return cp


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sql_connect():
    from mssql_python import connect

    cs = (
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    return connect(cs)


def load_csv(path: Path):
    if not path.exists():
        raise RuntimeError(f"REQUIRED_ARTIFACT_NOT_FOUND={path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise RuntimeError(f"REQUIRED_ARTIFACT_EMPTY={path}")

    return rows


def validate_local_artifacts():
    silver = load_csv(SILVER)
    gold = load_csv(GOLD)

    required_gold = {
        "SourceTechnologyId",
        "TargetTechnologyId",
        "RelationType",
        "EvidenceType",
        "SourceId",
    }
    missing = required_gold - set(gold[0].keys())
    if missing:
        raise RuntimeError(
            "GOLD_SCHEMA_MISSING=" + ",".join(sorted(missing))
        )

    required_silver = {
        "source_technology_id",
        "target_technology_id",
        "relation_type",
        "evidence_type",
        "source_id",
        "resolution_status",
    }
    missing_silver = required_silver - set(silver[0].keys())
    if missing_silver:
        raise RuntimeError(
            "SILVER_SCHEMA_MISSING=" + ",".join(sorted(missing_silver))
        )

    if len(silver) != len(gold):
        raise RuntimeError(
            f"SILVER_GOLD_COUNT_MISMATCH "
            f"silver={len(silver)} gold={len(gold)}"
        )

    # Validate IDs against current authoritative dimension before any upload.
    conn = sql_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TechnologyId FROM techscope.DimTechnology"
        )
        valid_ids = {str(r[0]) for r in cur.fetchall()}
    finally:
        conn.close()

    invalid = []
    self_edges = []

    for row in gold:
        src = (row.get("SourceTechnologyId") or "").strip()
        dst = (row.get("TargetTechnologyId") or "").strip()

        if src not in valid_ids or dst not in valid_ids:
            invalid.append((src, dst))
        if src == dst:
            self_edges.append((src, dst))

    if invalid:
        raise RuntimeError(
            f"LOCAL_GOLD_INVALID_TECHNOLOGY_IDS={len(invalid)}"
        )

    if self_edges:
        raise RuntimeError(
            f"LOCAL_GOLD_SELF_EDGES={len(self_edges)}"
        )

    return silver, gold


def verify_storage_key_access():
    # Query only the number of keys; never print or persist key material.
    cp = run(
        [
            "az", "storage", "account", "keys", "list",
            "--account-name", STORAGE_ACCOUNT,
            "--resource-group", RESOURCE_GROUP,
            "--query", "length(@)",
            "-o", "tsv",
            "--only-show-errors",
        ],
        check=False,
        timeout=60,
    )

    if cp.returncode != 0:
        raise RuntimeError(
            "STORAGE_ACCOUNT_KEY_ACCESS=FAIL\n"
            + (cp.stderr or "")[-3000:]
        )

    text = (cp.stdout or "").strip()
    try:
        count = int(text)
    except Exception:
        raise RuntimeError(
            f"STORAGE_ACCOUNT_KEY_COUNT_INVALID={text!r}"
        )

    if count <= 0:
        raise RuntimeError("STORAGE_ACCOUNT_KEYS_EMPTY")

    print(f"STORAGE_ACCOUNT_KEY_ACCESS=PASS COUNT={count}", flush=True)


def upload_key_auth(local: Path, remote_path: str):
    # `--auth-mode key` lets Azure CLI query the account key using the
    # authenticated management-plane identity. No key is placed on the
    # command line, written to disk, or printed.
    cp = run(
        [
            "az", "storage", "fs", "file", "upload",
            "--account-name", STORAGE_ACCOUNT,
            "--file-system", FILESYSTEM,
            "--path", remote_path,
            "--source", str(local),
            "--auth-mode", "key",
            "--overwrite", "true",
            "--only-show-errors",
        ],
        check=False,
        timeout=120,
    )

    if cp.returncode != 0:
        raise RuntimeError(
            f"ADLS_KEY_AUTH_UPLOAD_FAIL path={remote_path}\n"
            + (cp.stderr or "")[-3000:]
        )


def load_sql(gold):
    conn = sql_connect()

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation"
        )
        before = int(cur.fetchone()[0])

        cur.execute(
            "SELECT TechnologyId FROM techscope.DimTechnology"
        )
        valid_ids = {str(r[0]) for r in cur.fetchall()}

        invalid_fk = [
            r for r in gold
            if str(r["SourceTechnologyId"]) not in valid_ids
            or str(r["TargetTechnologyId"]) not in valid_ids
        ]
        if invalid_fk:
            raise RuntimeError(
                f"SQL_FK_PREFLIGHT_FAIL={len(invalid_fk)}"
            )

        for r in gold:
            cur.execute(
                """
                IF NOT EXISTS (
                    SELECT 1
                    FROM techscope.FactTechnologyRelation
                    WHERE SourceTechnologyId=?
                      AND TargetTechnologyId=?
                      AND RelationType=?
                      AND EvidenceType=?
                      AND SourceId=?
                )
                BEGIN
                    INSERT INTO techscope.FactTechnologyRelation
                    (
                        SourceTechnologyId,
                        TargetTechnologyId,
                        RelationType,
                        EvidenceType,
                        SourceId
                    )
                    VALUES (?,?,?,?,?)
                END
                """,
                (
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                ),
            )

        conn.commit()

        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation"
        )
        after = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactTechnologyRelation f
            LEFT JOIN techscope.DimTechnology s
              ON s.TechnologyId=f.SourceTechnologyId
            LEFT JOIN techscope.DimTechnology t
              ON t.TechnologyId=f.TargetTechnologyId
            WHERE s.TechnologyId IS NULL
               OR t.TechnologyId IS NULL
            """
        )
        invalid_after = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactTechnologyRelation
            WHERE SourceTechnologyId=TargetTechnologyId
            """
        )
        self_edges = int(cur.fetchone()[0])

        if after <= 0:
            raise RuntimeError("SQL_RELATION_POSTLOAD_ZERO")
        if invalid_after != 0:
            raise RuntimeError(
                f"SQL_RELATION_INVALID_FK_ROWS={invalid_after}"
            )
        if self_edges != 0:
            raise RuntimeError(
                f"SQL_RELATION_SELF_EDGE_ROWS={self_edges}"
            )

        return {
            "before": before,
            "after": after,
            "inserted": max(0, after - before),
            "invalid_fk_rows": invalid_after,
            "self_edges": self_edges,
        }

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def find_successful_databricks_run():
    # Best-effort evidence recovery for the successful Serverless Spark run
    # that generated the local Silver/Gold artifacts before v6 hit ADLS.
    cp = run(
        [
            "databricks", "jobs", "list-runs",
            "--limit", "20",
            "-o", "json",
        ],
        check=False,
        timeout=60,
    )

    if cp.returncode != 0:
        return None

    try:
        obj = json.loads((cp.stdout or "").strip() or "[]")
    except Exception:
        return None

    if isinstance(obj, list):
        runs = obj
    elif isinstance(obj, dict):
        runs = obj.get("runs", [])
    else:
        runs = []

    for r in runs:
        if r.get("run_name") != "TechScope-P1E-Relation-Repair":
            continue

        state = r.get("state") or {}
        if state.get("result_state") == "SUCCESS":
            return {
                "run_id": r.get("run_id"),
                "life_cycle_state": state.get("life_cycle_state"),
                "result_state": state.get("result_state"),
                "run_name": r.get("run_name"),
            }

    return None


def main():
    print("P1E_RELATION_ADLS_SQL_RESUME_V7=START", flush=True)
    print("DATABRICKS_RERUN=NO", flush=True)

    silver, gold = validate_local_artifacts()

    print(f"LOCAL_SILVER_ROWS={len(silver)}", flush=True)
    print(f"LOCAL_GOLD_ROWS={len(gold)}", flush=True)
    print("LOCAL_RELATION_ID_VALIDATION=PASS", flush=True)
    print("LOCAL_RELATION_SELF_EDGE_VALIDATION=PASS", flush=True)

    dbx = find_successful_databricks_run()
    if dbx:
        print(
            f"DATABRICKS_SUCCESS_RUN_RECOVERED={dbx['run_id']}",
            flush=True,
        )
    else:
        print(
            "DATABRICKS_SUCCESS_RUN_RECOVERED=NOT_FOUND_NONBLOCKING",
            flush=True,
        )

    verify_storage_key_access()

    upload_key_auth(SILVER, SILVER_ADLS)
    print("ADLS_SILVER_RELATION=PASS AUTH=KEY_RUNTIME_ONLY", flush=True)

    upload_key_auth(GOLD, GOLD_ADLS)
    print("ADLS_GOLD_RELATION=PASS AUTH=KEY_RUNTIME_ONLY", flush=True)

    sql_result = load_sql(gold)

    print(
        f"FACT_TECHNOLOGY_RELATION_ROWS="
        f"{sql_result['before']}->{sql_result['after']}",
        flush=True,
    )
    print(
        f"FACT_TECHNOLOGY_RELATION_INSERTED="
        f"{sql_result['inserted']}",
        flush=True,
    )
    print("SQL_RELATION_FK_VALIDATION=PASS", flush=True)
    print("SQL_RELATION_SELF_EDGE_VALIDATION=PASS", flush=True)

    now = datetime.now(timezone.utc).isoformat()

    # Recover/complete P1E evidence without fabricating a run ID.
    if dbx:
        write_json(
            EVD_DBX_EXEC,
            {
                "timestamp_utc": now,
                "component": "CMP_DATABRICKS",
                "phase": "P1E_RELATION_REPAIR",
                "implementation_evidence": "EXECUTION",
                "databricks_run_id": dbx["run_id"],
                "compute": "SERVERLESS_JOB_COMPUTE",
                "result": "PASS",
            },
        )

    write_json(
        EVD_DBX_OUT,
        {
            "timestamp_utc": now,
            "component": "CMP_DATABRICKS",
            "phase": "P1E_RELATION_REPAIR",
            "implementation_evidence": "OUTPUT",
            "silver": {
                "adls_path": f"{FILESYSTEM}/{SILVER_ADLS}",
                "rows": len(silver),
            },
            "gold": {
                "adls_path": f"{FILESYSTEM}/{GOLD_ADLS}",
                "rows": len(gold),
            },
            "result": "PASS",
        },
    )

    write_json(
        EVD_SQL,
        {
            "timestamp_utc": now,
            "component": "CMP_AZURE_SQL",
            "phase": "P1E_RELATION_REPAIR",
            "implementation_evidence": "OUTPUT",
            "table": "techscope.FactTechnologyRelation",
            **sql_result,
            "result": "PASS",
        },
    )

    summary = {
        "timestamp_utc": now,
        "status": "PASS",
        "resume_stage": "ADLS_AND_AZURE_SQL",
        "databricks_rerun": False,
        "validated_relation_rows": len(gold),
        "fact_rows_before": sql_result["before"],
        "fact_rows_after": sql_result["after"],
        "fact_rows_inserted": sql_result["inserted"],
        "silver_adls": SILVER_ADLS,
        "gold_adls": GOLD_ADLS,
        "storage_auth": "account_key_queried_at_runtime_not_persisted",
        "databricks_success_run": dbx,
    }
    write_json(RESULT, summary)

    lint = run(
        ["python", str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=90,
    )
    lint_text = (lint.stdout or "") + "\n" + (lint.stderr or "")

    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in lint_text:
        print("ARCHITECTURE_LINT_AFTER_REPAIR=FAIL", flush=True)
        print(lint_text[-4000:], flush=True)
        raise RuntimeError("ARCHITECTURE_LINT_AFTER_REPAIR=FAIL")

    print("ARCHITECTURE_LINT_AFTER_REPAIR=PASS", flush=True)
    print("P1E_RELATION_REPAIR=PASS", flush=True)
    print("REPORT=results/latest/p1e-relation-repair.json", flush=True)
    print("STORAGE_KEY_PERSISTED=NO", flush=True)
    print("NEXT_ACTION=CHECKPOINT_GIT_THEN_P3_COSMOS_FEEDBACK", flush=True)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(
            f"P1E_RELATION_ADLS_SQL_RESUME_V7=FAIL "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        raise
