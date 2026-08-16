#!/usr/bin/env python3
from __future__ import annotations

import json
import secrets
import string
from pathlib import Path

import p1d_cloud_data_e2e as p1d

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "generated" / "runtime-config.json"
COMPONENTS = ROOT / "results" / "latest" / "p1d-component-results.json"
SUMMARY = ROOT / "results" / "latest" / "p1d-summary.json"


def password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%_-"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(28))
        if (
            any(c.isupper() for c in value)
            and any(c.islower() for c in value)
            and any(c.isdigit() for c in value)
            and any(c in "!@#%_-" for c in value)
        ):
            return value


def main() -> int:
    if not RUNTIME.exists():
        raise SystemExit("P1D_RESUME=FAIL runtime-config.json missing")

    runtime = json.loads(RUNTIME.read_text(encoding="utf-8-sig"))
    required = [
        "resource_group",
        "storage_account",
        "file_system",
        "databricks_workspace",
        "databricks_workspace_url",
        "sql_server",
        "sql_server_fqdn",
        "sql_database",
        "sql_admin_login",
    ]
    missing = [k for k in required if not runtime.get(k)]
    if missing:
        raise SystemExit("P1D_RESUME=FAIL runtime keys missing: " + ",".join(missing))

    print("P1D_RESUME_SCOPE=DATABRICKS_AND_AZURE_SQL_ONLY", flush=True)
    print("P1D_RESUME_PROVISION=SKIP_REUSE", flush=True)
    print("P1D_RESUME_ADLS=SKIP_ALREADY_PASS", flush=True)
    print("P1D_RESUME_ADF=SKIP_ALREADY_PASS", flush=True)

    # Re-establish a known ephemeral SQL admin password because the original
    # password was deliberately never persisted after v3 provisioning.
    sql_password = password()
    print("SQL_ADMIN_PASSWORD_ROTATE=START", flush=True)
    cp = p1d.run(
        [
            "az", "sql", "server", "update",
            "--resource-group", runtime["resource_group"],
            "--name", runtime["sql_server"],
            "--admin-password", sql_password,
            "--only-show-errors",
            "-o", "none",
        ],
        timeout=180,
        secret=True,
    )
    if cp.returncode != 0:
        print("SQL_ADMIN_PASSWORD_ROTATE=FAIL", flush=True)
        print((cp.stderr or cp.stdout)[-1500:], flush=True)
        return 2
    print("SQL_ADMIN_PASSWORD_ROTATE=PASS", flush=True)

    _, storage_key = p1d.storage_env(runtime)
    sql_user = runtime["sql_admin_login"]

    components = {
        "CMP_ADLS": "PASS",
        "CMP_ADF": "PASS",
        "CMP_DATABRICKS": "PENDING",
        "CMP_AZURE_SQL": "PENDING",
    }
    blockers: list[str] = []

    if p1d.run_databricks(runtime, storage_key, sql_user, sql_password):
        components["CMP_DATABRICKS"] = "PASS"
        if p1d.verify_sql(runtime, sql_user, sql_password):
            components["CMP_AZURE_SQL"] = "PASS"
        else:
            blockers.append("Azure SQL direct verification")
    else:
        blockers.append("Databricks job execution")
        blockers.append("Azure SQL load depends on Databricks job")

    p1d.write_json(COMPONENTS, {
        "timestamp": p1d.now(),
        "components": components,
        "blockers": blockers,
    })
    p1d.write_json(SUMMARY, {
        "timestamp": p1d.now(),
        "status": "PASS" if not blockers else "PENDING",
        "components": components,
        "blockers": blockers,
        "runtime": runtime,
        "resume_scope": "DATABRICKS_AND_AZURE_SQL_ONLY",
        "secrets_persisted": False,
    })

    print(
        "P1D_RESUME_RESULT=" + ("PASS" if not blockers else "PENDING"),
        flush=True,
    )
    print("P1D_COMPONENTS=" + json.dumps(components, ensure_ascii=False), flush=True)
    print(f"BLOCKER_COUNT={len(blockers)}", flush=True)
    print("SECRETS_WRITTEN_TO_REPO=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
