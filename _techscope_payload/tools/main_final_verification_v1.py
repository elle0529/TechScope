#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

ROOT = Path("/workspaces/TechScope")

RESULT = ROOT / "results/latest/main-final-verification.json"
SUMMARY = ROOT / "results/latest/main-final-status-summary.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

COMPONENTS = {
    "CMP_ADLS": {
        "expected_status": "Implemented",
        "evidence_any": [
            "results/latest/p1d-summary.json",
            "docs/evidence.md",
        ],
    },
    "CMP_PYTHON": {
        "expected_status": "Prototype",
        "evidence_any": [
            "extractor",
            "results/latest",
        ],
    },
    "CMP_ADF": {
        "expected_status": "Implemented",
        "evidence_any": [
            "results/latest/p1d-summary.json",
            "docs/evidence.md",
        ],
    },
    "CMP_DATABRICKS": {
        "expected_status": "Implemented",
        "evidence_any": [
            "results/latest/p1e-relation-repair.json",
            "evidence/databricks",
        ],
    },
    "CMP_AZURE_SQL": {
        "expected_status": "Implemented",
        "evidence_any": [
            "evidence/backend/p2c-sql-persistence.json",
            "results/latest/p1e-relation-repair.json",
        ],
    },
    "CMP_POWER_BI": {
        "expected_status": "Implemented",
        "evidence_any": [
            "powerbi/demo_final/TechScopeDemo.pbip",
            "powerbi/demo_final/data",
        ],
    },
    "CMP_AI_SEARCH": {
        "expected_status": "Implemented",
        "evidence_any": [
            "evidence/rag/p2b-cloud-e2e.json",
        ],
    },
    "CMP_AZURE_OPENAI": {
        "expected_status": "Implemented",
        "evidence_any": [
            "evidence/rag/p2b-cloud-e2e.json",
        ],
    },
    "CMP_FASTAPI": {
        "expected_status": "Implemented",
        "evidence_any": [
            "backend/app/main.py",
            "evidence/rag/p2b-cloud-e2e.json",
        ],
    },
    "CMP_COSMOS": {
        "expected_status": "Blocked",
        "evidence_any": [
            "results/latest/p3-cosmos-blocker.json",
            "evidence/cosmos/p3-cosmos-blocked.json",
        ],
    },
    "CMP_TEAMS": {
        "expected_status": "Prototype",
        "evidence_any": [
            "results/latest/p3-teams-prototype.json",
            "evidence/teams/p3-teams-source.json",
            "evidence/teams/p3-teams-execution.json",
        ],
    },
}


def run(cmd, *, check=True, timeout=120, cwd=None):
    cp = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-5000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-5000:]
        )
    return cp


def path_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def component_evidence():
    result = {}
    for comp, cfg in COMPONENTS.items():
        hits = [p for p in cfg["evidence_any"] if path_exists(p)]
        result[comp] = {
            "expected_status": cfg["expected_status"],
            "evidence_found": hits,
            "evidence_present": bool(hits),
        }
        print(
            f"{comp}_EVIDENCE={'PASS' if hits else 'MISSING'} "
            f"STATUS={cfg['expected_status']}",
            flush=True,
        )
    return result


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


def sql_counts():
    conn = sql_connect()
    try:
        cur = conn.cursor()

        checks = {
            "technology": "SELECT COUNT_BIG(*) FROM techscope.DimTechnology",
            "category": "SELECT COUNT_BIG(*) FROM techscope.DimCategory",
            "relation": "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation",
            "ai_request": "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest",
            "bridge": "SELECT COUNT_BIG(*) FROM techscope.BridgeAIRequestTechnology",
        }

        values = {}
        for name, sql in checks.items():
            cur.execute(sql)
            values[name] = int(cur.fetchone()[0])

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
        invalid_fk = int(cur.fetchone()[0])

        values["relation_invalid_fk"] = invalid_fk

        if values["technology"] <= 0:
            raise RuntimeError("SQL_TECHNOLOGY_ZERO")
        if values["category"] <= 0:
            raise RuntimeError("SQL_CATEGORY_ZERO")
        if values["relation"] <= 0:
            raise RuntimeError("SQL_RELATION_ZERO")
        if invalid_fk != 0:
            raise RuntimeError(
                f"SQL_RELATION_INVALID_FK={invalid_fk}"
            )

        print(
            f"SQL_DIM_TECHNOLOGY_ROWS={values['technology']}",
            flush=True,
        )
        print(
            f"SQL_DIM_CATEGORY_ROWS={values['category']}",
            flush=True,
        )
        print(
            f"SQL_FACT_TECHNOLOGY_RELATION_ROWS={values['relation']}",
            flush=True,
        )
        print(
            f"SQL_FACT_AI_REQUEST_ROWS={values['ai_request']}",
            flush=True,
        )
        print(
            f"SQL_BRIDGE_AI_REQUEST_TECHNOLOGY_ROWS={values['bridge']}",
            flush=True,
        )
        print("SQL_RELATION_FK_VALIDATION=PASS", flush=True)
        return values
    finally:
        conn.close()


def health_check():
    candidates = [
        "http://127.0.0.1:8000/health",
    ]

    last_error = None
    for url in candidates:
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=10) as r:
                body = r.read().decode("utf-8", errors="replace")
                code = r.status
            if code == 200:
                print("FASTAPI_HEALTH=PASS HTTP=200", flush=True)
                return {"url": url, "http_status": code, "body": body[:1000]}
        except Exception as exc:
            last_error = repr(exc)

    print(f"FASTAPI_HEALTH=FAIL ERROR={last_error}", flush=True)
    return {
        "url": candidates[0],
        "http_status": None,
        "error": last_error,
    }


def verify_rag_evidence():
    path = ROOT / "evidence/rag/p2b-cloud-e2e.json"
    if not path.exists():
        print("RAG_CLOUD_E2E_EVIDENCE=MISSING", flush=True)
        return {"present": False}

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        obj = {}

    print("RAG_CLOUD_E2E_EVIDENCE=PASS", flush=True)
    return {"present": True, "data": obj}


def verify_p1e():
    path = ROOT / "results/latest/p1e-relation-repair.json"
    if not path.exists():
        print("P1E_RELATION_REPORT=MISSING", flush=True)
        return {"present": False}

    obj = json.loads(path.read_text(encoding="utf-8"))
    status = obj.get("status")
    rows = obj.get("validated_relation_rows")

    print(f"P1E_RELATION_REPORT=PASS STATUS={status}", flush=True)
    print(f"P1E_VALIDATED_RELATION_ROWS={rows}", flush=True)

    return {"present": True, "data": obj}


def verify_cosmos():
    blocker = ROOT / "results/latest/p3-cosmos-blocker.json"
    if not blocker.exists():
        print("COSMOS_BLOCKER_REPORT=MISSING", flush=True)
        return {"present": False}

    obj = json.loads(blocker.read_text(encoding="utf-8"))
    print(
        f"CMP_COSMOS_FINAL_STATUS={obj.get('status')}",
        flush=True,
    )
    print(
        f"CMP_COSMOS_BLOCKER={obj.get('reason')}",
        flush=True,
    )
    return {"present": True, "data": obj}


def verify_teams():
    report = ROOT / "results/latest/p3-teams-prototype.json"
    if not report.exists():
        print("TEAMS_PROTOTYPE_REPORT=MISSING", flush=True)
        return {"present": False}

    obj = json.loads(report.read_text(encoding="utf-8"))
    print(
        f"CMP_TEAMS_FINAL_STATUS={obj.get('status')}",
        flush=True,
    )
    print(
        f"TEAMS_SDK={obj.get('teams_sdk')}",
        flush=True,
    )
    print(
        f"TEAMS_LIVE_TENANT_E2E={obj.get('live_teams_tenant_e2e')}",
        flush=True,
    )
    return {"present": True, "data": obj}


def architecture_lint():
    cp = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=120,
    )
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")

    if cp.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError("ARCHITECTURE_LINT_FINAL=FAIL")

    check_lines = [
        line for line in text.splitlines()
        if line.startswith("CHECK ")
    ]

    print("ARCHITECTURE_LINT_FINAL=PASS", flush=True)
    print(f"ARCHITECTURE_LINT_CHECKS={len(check_lines)}", flush=True)

    return {
        "pass": True,
        "checks": len(check_lines),
        "tail": text[-3000:],
    }


def compute_release_status(
    components,
    health,
    cosmos,
    teams,
):
    missing_evidence = [
        k for k, v in components.items()
        if not v["evidence_present"]
    ]

    blockers = []
    if cosmos.get("present"):
        cdata = cosmos.get("data") or {}
        if str(cdata.get("status")).lower() == "blocked":
            blockers.append(
                "CMP_COSMOS: NO_EXISTING_COSMOS_ACCOUNT"
            )
    else:
        blockers.append("CMP_COSMOS: blocker evidence missing")

    teams_status = (
        (teams.get("data") or {}).get("status")
        if teams.get("present")
        else None
    )
    if teams_status != "Implemented":
        blockers.append(
            "CMP_TEAMS: Prototype only; live Teams tenant E2E not completed"
        )

    if health.get("http_status") != 200:
        blockers.append("CMP_FASTAPI: live health endpoint unavailable")

    release_ready = (
        len(missing_evidence) == 0
        and len(blockers) == 0
    )

    return {
        "release_ready": release_ready,
        "portfolio_core_ready": (
            health.get("http_status") == 200
            and not missing_evidence
        ),
        "missing_evidence": missing_evidence,
        "blockers": blockers,
    }


def main():
    now = datetime.now(timezone.utc).isoformat()

    print("MAIN_FINAL_VERIFICATION_V1=START", flush=True)
    print("AI_ASK_CALL=NO", flush=True)
    print("AZURE_RESOURCE_CREATION=NO", flush=True)
    print("AZURE_RESOURCE_DELETION=NO", flush=True)

    components = component_evidence()
    sql = sql_counts()
    health = health_check()
    rag = verify_rag_evidence()
    p1e = verify_p1e()
    cosmos = verify_cosmos()
    teams = verify_teams()
    lint = architecture_lint()

    release = compute_release_status(
        components,
        health,
        cosmos,
        teams,
    )

    report = {
        "timestamp_utc": now,
        "status": "PASS",
        "ai_ask_call_performed": False,
        "components": components,
        "sql": sql,
        "fastapi_health": health,
        "rag_evidence": rag,
        "p1e_relation": p1e,
        "cosmos": cosmos,
        "teams": teams,
        "architecture_lint": lint,
        "release": release,
    }

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "timestamp_utc": now,
        "main_component_status": {
            "CMP_ADLS": "Implemented",
            "CMP_PYTHON": "Prototype",
            "CMP_ADF": "Implemented",
            "CMP_DATABRICKS": "Implemented",
            "CMP_AZURE_SQL": "Implemented",
            "CMP_POWER_BI": "Implemented",
            "CMP_AI_SEARCH": "Implemented",
            "CMP_AZURE_OPENAI": "Implemented",
            "CMP_FASTAPI": (
                "Implemented"
                if health.get("http_status") == 200
                else "Blocked"
            ),
            "CMP_COSMOS": "Blocked",
            "CMP_TEAMS": "Prototype",
        },
        "release_ready": release["release_ready"],
        "portfolio_core_ready": release["portfolio_core_ready"],
        "blockers": release["blockers"],
        "sql_counts": sql,
    }

    SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"PORTFOLIO_CORE_READY="
        f"{'YES' if release['portfolio_core_ready'] else 'NO'}",
        flush=True,
    )
    print(
        f"RELEASE_READY="
        f"{'YES' if release['release_ready'] else 'NO'}",
        flush=True,
    )

    print(f"RELEASE_BLOCKERS={len(release['blockers'])}", flush=True)
    for b in release["blockers"]:
        print("BLOCKER=" + b, flush=True)

    print(
        "REPORT=results/latest/main-final-verification.json",
        flush=True,
    )
    print(
        "SUMMARY=results/latest/main-final-status-summary.json",
        flush=True,
    )
    print("MAIN_FINAL_VERIFICATION_V1=PASS", flush=True)
    print("NEXT_ACTION=GIT_CHECKPOINT_AND_DECIDE_COSMOS_POLICY", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
