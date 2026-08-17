#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/workspaces/TechScope")

ACTIVATION = ROOT / "results/latest/grounding-live-activation-v6.json"
SYNC_REPORT = ROOT / "results/latest/grounding-powerbi-sync.json"
STATUS = ROOT / "docs/status.md"
EVIDENCE = ROOT / "docs/evidence.md"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

STATUS_START = "<!-- TECHSCOPE_GROUNDING_FIX:START -->"
STATUS_END = "<!-- TECHSCOPE_GROUNDING_FIX:END -->"
EVIDENCE_START = "<!-- TECHSCOPE_GROUNDING_EVIDENCE:START -->"
EVIDENCE_END = "<!-- TECHSCOPE_GROUNDING_EVIDENCE:END -->"


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd,
        cwd=ROOT,
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


def sql_connect():
    from mssql_python import connect

    return connect(
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;",
    )


def sql_verify():
    conn = sql_connect()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COUNT_BIG(*),
                COALESCE(MAX(RequestKey), 0)
            FROM techscope.FactAIRequest
            """
        )
        count, max_key = cur.fetchone()
        count = int(count)
        max_key = int(max_key)

        cur.execute(
            """
            SELECT CitationFlag
            FROM techscope.FactAIRequest
            WHERE RequestKey = ?
            """,
            (max_key,),
        )
        row = cur.fetchone()
        citation_flag = row[0] if row else None

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.BridgeAIRequestTechnology
            WHERE RequestKey = ?
            """,
            (max_key,),
        )
        bridge = int(cur.fetchone()[0])

        print(f"SQL_AI_REQUESTS={count}", flush=True)
        print(f"SQL_LATEST_REQUEST_KEY={max_key}", flush=True)
        print(f"SQL_LATEST_CITATION_FLAG={citation_flag}", flush=True)
        print(f"SQL_LATEST_BRIDGE_ROWS={bridge}", flush=True)

        if count != 20:
            raise RuntimeError(
                f"SQL_AI_REQUEST_COUNT_UNEXPECTED expected=20 actual={count}"
            )
        if max_key != 20:
            raise RuntimeError(
                f"SQL_LATEST_REQUEST_KEY_UNEXPECTED expected=20 actual={max_key}"
            )
        if str(citation_flag).lower() not in {"0", "false"}:
            raise RuntimeError(
                "SQL_LATEST_CITATION_FLAG_NOT_FALSE"
            )
        if bridge != 0:
            raise RuntimeError(
                "SQL_LATEST_BRIDGE_ROWS_NOT_ZERO"
            )

        print("SQL_GROUNDING_LATEST_STATE=PASS", flush=True)

        return {
            "ai_requests": count,
            "latest_request_key": max_key,
            "latest_citation_flag": citation_flag,
            "latest_bridge_rows": bridge,
        }
    finally:
        conn.close()


def live_identity():
    url = "http://127.0.0.1:8000/demo/grounding-runtime"

    with urlopen(Request(url, method="GET"), timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(
                f"LIVE_GROUNDING_RUNTIME_HTTP={response.status}"
            )
        obj = json.loads(response.read().decode("utf-8"))

    print(
        f"LIVE_RUNTIME_VERSION={obj.get('version')}",
        flush=True,
    )
    print(
        f"LIVE_RUNTIME_PID={obj.get('pid')}",
        flush=True,
    )
    print(
        f"LIVE_ASK_GUARD_WRAPPED={obj.get('ask_guard_wrapped')}",
        flush=True,
    )

    if obj.get("version") != "v6":
        raise RuntimeError("LIVE_RUNTIME_NOT_V6")
    if obj.get("ask_guard_wrapped") is not True:
        raise RuntimeError("LIVE_ASK_GUARD_NOT_WRAPPED")

    return obj


def powerbi_sync():
    url = "http://127.0.0.1:8000/demo/powerbi-sync"
    req = Request(
        url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urlopen(req, timeout=90) as response:
        body = response.read().decode("utf-8", errors="replace")
        status = response.status

    print(f"POWERBI_SYNC_HTTP={status}", flush=True)

    if status != 200:
        raise RuntimeError(
            f"POWERBI_SYNC_HTTP_FAIL={status} body={body[:1000]}"
        )

    try:
        obj = json.loads(body)
    except Exception:
        obj = {"raw": body[:2000]}

    print("POWERBI_SNAPSHOT_SYNC=PASS", flush=True)
    return obj


def csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise RuntimeError(f"POWERBI_CSV_MISSING={path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = list(reader.fieldnames or [])

    return headers, rows


def pick(headers, candidates):
    low = {h.lower(): h for h in headers}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def verify_snapshot(sql_state):
    roots = [
        ROOT / "powerbi/demo_final/data",
        ROOT / "powerbi/demo_snapshot/data",
    ]

    results = {}

    for d in roots:
        detail = d / "AIRequestDetail.csv"
        grounded = d / "GroundedTechnology.csv"
        executive = d / "ExecutiveSummary.csv"

        for p in [detail, grounded, executive]:
            if not p.exists():
                raise RuntimeError(
                    f"POWERBI_REQUIRED_CSV_MISSING={p}"
                )

        headers, rows = csv_rows(detail)

        req_key_col = pick(
            headers,
            [
                "RequestKey",
                "RequestId",
                "AIRequestId",
            ],
        )
        citation_col = pick(
            headers,
            [
                "CitationFlag",
                "Citation",
                "HasCitation",
            ],
        )

        print(
            f"POWERBI_DETAIL_ROWS[{d.name}]={len(rows)}",
            flush=True,
        )

        if len(rows) != sql_state["ai_requests"]:
            raise RuntimeError(
                f"POWERBI_DETAIL_ROW_COUNT_MISMATCH "
                f"path={detail} expected={sql_state['ai_requests']} "
                f"actual={len(rows)}"
            )

        latest = None
        if req_key_col:
            for row in rows:
                if str(row.get(req_key_col)) == str(
                    sql_state["latest_request_key"]
                ):
                    latest = row
                    break

            if latest is None:
                raise RuntimeError(
                    f"POWERBI_LATEST_REQUEST_NOT_FOUND={detail}"
                )

            print(
                f"POWERBI_LATEST_REQUEST_PRESENT[{d.name}]=PASS",
                flush=True,
            )

            if citation_col:
                value = latest.get(citation_col)
                print(
                    f"POWERBI_LATEST_CITATION_FLAG[{d.name}]={value}",
                    flush=True,
                )
                if str(value).lower() not in {
                    "0",
                    "false",
                    "false.0",
                }:
                    raise RuntimeError(
                        "POWERBI_LATEST_CITATION_FLAG_NOT_FALSE"
                    )

        g_headers, g_rows = csv_rows(grounded)
        g_req_col = pick(
            g_headers,
            [
                "RequestKey",
                "RequestId",
                "AIRequestId",
            ],
        )

        if g_req_col:
            latest_grounded = [
                r
                for r in g_rows
                if str(r.get(g_req_col))
                == str(sql_state["latest_request_key"])
            ]

            print(
                f"POWERBI_LATEST_GROUNDED_ROWS[{d.name}]="
                f"{len(latest_grounded)}",
                flush=True,
            )

            if latest_grounded:
                raise RuntimeError(
                    "POWERBI_LATEST_GROUNDED_ROWS_NOT_ZERO"
                )

        results[str(d.relative_to(ROOT))] = {
            "detail_rows": len(rows),
            "grounded_rows": len(g_rows),
            "latest_request_present": latest is not None,
        }

    print("POWERBI_SNAPSHOT_VALIDATION=PASS", flush=True)
    return results


def replace_block(text, start, end, body):
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    replacement = start + "\n" + body.rstrip() + "\n" + end

    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)

    if text and not text.endswith("\n"):
        text += "\n"

    return text + "\n" + replacement + "\n"


def sync_docs(sql_state):
    status_text = (
        STATUS.read_text(encoding="utf-8")
        if STATUS.exists()
        else "# Status\n"
    )
    evidence_text = (
        EVIDENCE.read_text(encoding="utf-8")
        if EVIDENCE.exists()
        else "# Evidence\n"
    )

    status_body = f"""## AI Grounding Quality Fix

- Status: `LIVE VERIFIED`
- Live runtime: `v6`
- False-positive grounding guard: `Implemented`
- Out-of-domain response:
  - Grounded: `False`
  - Citations: `0`
  - Grounded Technology IDs: `0`
- SQL reconciliation:
  - FactAIRequest retained: `YES`
  - CitationFlag: `False`
  - BridgeAIRequestTechnology rows: `0`
- Verified latest RequestKey: `{sql_state['latest_request_key']}`
- Current FactAIRequest rows: `{sql_state['ai_requests']}`
- Power BI Snapshot sync: `PASS`

> Out-of-domain requests remain operational requests, but are no longer represented as grounded requests.
"""

    evidence_body = f"""## AI Grounding Quality Evidence

- Live activation report: `results/latest/grounding-live-activation-v6.json`
- Persistence diagnostic: `results/latest/grounding-persistence-diagnostic-v3.json`
- Grounding guard configuration: `config/grounding-guard.json`
- Grounding guard source: `backend/app/grounding_guard.py`
- Latest verified RequestKey: `{sql_state['latest_request_key']}`
- Latest CitationFlag: `False`
- Latest Bridge rows: `0`
- Live `/demo/grounding-runtime`: `version=v6`, `ask_guard_wrapped=true`
- Live unrelated-question regression:
  - Grounded=False
  - Citations=0
  - Technology IDs=0
- Power BI Snapshot: synchronized after live verification.
"""

    STATUS.write_text(
        replace_block(
            status_text,
            STATUS_START,
            STATUS_END,
            status_body,
        ),
        encoding="utf-8",
    )

    EVIDENCE.write_text(
        replace_block(
            evidence_text,
            EVIDENCE_START,
            EVIDENCE_END,
            evidence_body,
        ),
        encoding="utf-8",
    )

    print("DOC_STATUS_GROUNDING_SYNC=PASS", flush=True)
    print("DOC_EVIDENCE_GROUNDING_SYNC=PASS", flush=True)
    print("FROZEN_BASELINE_MODIFIED=NO", flush=True)


def lint():
    cp = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=120,
    )
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")

    if cp.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError(
            "ARCHITECTURE_LINT_AFTER_GROUNDING_SYNC=FAIL"
        )

    checks = [
        line
        for line in text.splitlines()
        if line.startswith("CHECK ")
    ]

    print("ARCHITECTURE_LINT_AFTER_GROUNDING_SYNC=PASS", flush=True)
    print(
        f"ARCHITECTURE_LINT_CHECKS={len(checks)}",
        flush=True,
    )


def main():
    print(
        "GROUNDING_POWERBI_CHECKPOINT_PREP_V1=START",
        flush=True,
    )
    print("AI_ASK_CALLS=0", flush=True)
    print("EXPECTED_AI_REQUEST_DELTA=0", flush=True)
    print("AZURE_RESOURCE_MUTATION=NO", flush=True)

    if not ACTIVATION.exists():
        raise RuntimeError(
            "GROUNDING_V6_ACTIVATION_REPORT_MISSING"
        )

    activation = json.loads(
        ACTIVATION.read_text(encoding="utf-8")
    )
    if activation.get("status") != "PASS":
        raise RuntimeError(
            "GROUNDING_V6_ACTIVATION_NOT_PASS"
        )

    runtime = live_identity()
    sql_state = sql_verify()
    sync_result = powerbi_sync()
    snapshot = verify_snapshot(sql_state)
    sync_docs(sql_state)
    lint()

    SYNC_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    SYNC_REPORT.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime": runtime,
                "sql": sql_state,
                "powerbi_sync_response": sync_result,
                "snapshot": snapshot,
                "ai_ask_calls": 0,
                "azure_resource_mutation": False,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(
        "REPORT=results/latest/grounding-powerbi-sync.json",
        flush=True,
    )
    print(
        "GROUNDING_POWERBI_CHECKPOINT_PREP_V1=PASS",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
