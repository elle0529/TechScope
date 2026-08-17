#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/workspaces/TechScope")
RG = "rg-techscope-dev-239bd206"
SEARCH_SERVICE = "srch-techscope-dev-239bd206-b1"
SEARCH_INDEX = "techscope-chunks"
API_VERSION = "2024-07-01"

MAIN = ROOT / "backend/app/main.py"
GUARD = ROOT / "backend/app/grounding_guard.py"
CONFIG = ROOT / "config/grounding-guard.json"
TEMPLATE = ROOT / "generated/grounding-guard-installer/grounding_guard.py"
REPORT = ROOT / "results/latest/grounding-false-positive-fix.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

POSITIVE_QUESTIONS = [
    "What role does Azure Databricks play in TechScope?",
    "How is Power BI used in TechScope?",
    "Azure SQL과 Databricks는 TechScope에서 어떻게 연결돼?",
]

NEGATIVE_QUESTIONS = [
    "포유류의 대표적인 동물은 뭐가있어?",
    "프랑스의 수도는 어디야?",
    "김치찌개 만드는 방법 알려줘",
]

ALIASES = [
    "Azure Databricks",
    "Databricks",
    "Power BI",
    "Azure SQL",
    "Azure SQL Database",
    "Azure Data Factory",
    "ADF",
    "Azure AI Search",
    "Azure OpenAI",
    "Azure Machine Learning",
    "Azure ML",
    "Azure Synapse Analytics",
    "Synapse",
    "Azure Data Lake Storage Gen2",
    "ADLS Gen2",
    "Data Lake Gen2",
    "Cosmos DB",
    "Azure Cosmos DB",
    "Microsoft Teams",
    "Teams",
    "SSAS",
    "SQL Server Analysis Services",
    "Analysis Services",
    "TechScope",
]


def run(cmd, *, check=True, timeout=180, cwd=None):
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
            + (cp.stdout or "")[-6000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-6000:]
        )
    return cp


def search_key():
    commands = [
        [
            "az", "search", "service", "query-key", "list",
            "--resource-group", RG,
            "--search-service-name", SEARCH_SERVICE,
            "--query", "[0].key",
            "-o", "tsv",
            "--only-show-errors",
        ],
        [
            "az", "search", "query-key", "list",
            "--resource-group", RG,
            "--service-name", SEARCH_SERVICE,
            "--query", "[0].key",
            "-o", "tsv",
            "--only-show-errors",
        ],
    ]

    for cmd in commands:
        cp = run(cmd, check=False, timeout=60)
        key = (cp.stdout or "").strip()
        if cp.returncode == 0 and key:
            return key

    raise RuntimeError("SEARCH_QUERY_KEY_ACCESS=FAIL")


def score(question: str, key: str) -> float:
    url = (
        f"https://{SEARCH_SERVICE}.search.windows.net/"
        f"indexes/{SEARCH_INDEX}/docs/search?api-version={API_VERSION}"
    )
    req = Request(
        url,
        data=json.dumps(
            {"search": question, "top": 5, "count": True}
        ).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "api-key": key,
        },
    )

    with urlopen(req, timeout=30) as response:
        obj = json.loads(response.read().decode("utf-8"))

    scores = []
    for row in obj.get("value") or []:
        try:
            scores.append(float(row.get("@search.score") or 0.0))
        except Exception:
            pass
    return max(scores) if scores else 0.0


def calibrate():
    key = search_key()
    print("SEARCH_QUERY_KEY_ACCESS=PASS KEY_PERSISTED=NO", flush=True)

    positive = []
    negative = []

    for q in POSITIVE_QUESTIONS:
        s = score(q, key)
        positive.append({"question": q, "max_score": s})
        print(f"CALIBRATION_POSITIVE_SCORE={s:.6f}", flush=True)

    for q in NEGATIVE_QUESTIONS:
        s = score(q, key)
        negative.append({"question": q, "max_score": s})
        print(f"CALIBRATION_NEGATIVE_SCORE={s:.6f}", flush=True)

    min_pos = min(x["max_score"] for x in positive)
    max_neg = max(x["max_score"] for x in negative)

    separated = min_pos > max_neg
    if separated:
        threshold = (min_pos + max_neg) / 2.0
        method = "MIDPOINT_SEPARATED_CALIBRATION"
    else:
        threshold = max_neg * 1.20
        method = "NEGATIVE_CEILING_WITH_TECH_TERM_OVERRIDE"

    if threshold <= 0:
        raise RuntimeError("GROUNDING_THRESHOLD_INVALID")

    print(f"CALIBRATION_MIN_POSITIVE={min_pos:.6f}", flush=True)
    print(f"CALIBRATION_MAX_NEGATIVE={max_neg:.6f}", flush=True)
    print(f"GROUNDING_THRESHOLD={threshold:.6f}", flush=True)
    print(f"CALIBRATION_SEPARATED={'YES' if separated else 'NO'}", flush=True)

    return {
        "threshold": threshold,
        "method": method,
        "positive": positive,
        "negative": negative,
        "separated": separated,
    }


def install(calibration):
    if not TEMPLATE.exists():
        raise RuntimeError("GROUNDING_GUARD_TEMPLATE_NOT_FOUND")

    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        json.dumps(
            {
                "search_service": SEARCH_SERVICE,
                "search_index": SEARCH_INDEX,
                "resource_group": RG,
                "api_version": API_VERSION,
                "threshold": calibration["threshold"],
                "calibration_method": calibration["method"],
                "technology_aliases": ALIASES,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    shutil.copy2(TEMPLATE, GUARD)

    text = MAIN.read_text(encoding="utf-8")
    import_line = "from .grounding_guard import install_grounding_guard"
    call_line = "install_grounding_guard(app)"

    if import_line not in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, import_line)
        text = "\n".join(lines) + "\n"

    if call_line not in text:
        marker = '\nif __name__ == "__main__":'
        if marker in text:
            text = text.replace(
                marker,
                "\n" + call_line + marker,
                1,
            )
        else:
            text = text.rstrip() + "\n\n" + call_line + "\n"

    MAIN.write_text(text, encoding="utf-8")

    print("GROUNDING_GUARD_SOURCE=PASS", flush=True)
    print("GROUNDING_GUARD_CONFIG=PASS", flush=True)
    print("FASTAPI_ASK_GUARD_WIRING=PASS", flush=True)


def compile_and_lint():
    for path in [GUARD, MAIN]:
        cp = run(
            [sys.executable, "-m", "py_compile", str(path)],
            check=False,
            timeout=30,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"PY_COMPILE_FAIL={path}\n{cp.stderr}"
            )
    print("GROUNDING_GUARD_COMPILE=PASS", flush=True)

    lint = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=120,
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")
    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError("GROUNDING_GUARD_ARCHITECTURE_LINT=FAIL")

    print("GROUNDING_GUARD_ARCHITECTURE_LINT=PASS", flush=True)


def sql_request_count():
    from mssql_python import connect

    conn = connect(
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def wait_health(port: int, process: subprocess.Popen):
    url = f"http://127.0.0.1:{port}/health"
    started = time.monotonic()

    while time.monotonic() - started < 45:
        if process.poll() is not None:
            out, err = process.communicate(timeout=5)
            raise RuntimeError(
                "TEMP_FASTAPI_EXITED\n"
                + (out or "")[-3000:]
                + "\n"
                + (err or "")[-3000:]
            )
        try:
            with urlopen(Request(url, method="GET"), timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("TEMP_FASTAPI_HEALTH_TIMEOUT")


def call_ask(port: int, question: str) -> dict:
    url = f"http://127.0.0.1:{port}/ask"
    req = Request(
        url,
        data=json.dumps({"question": question}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=120) as r:
        if r.status != 200:
            raise RuntimeError(f"ASK_HTTP_STATUS={r.status}")
        return json.loads(r.read().decode("utf-8"))


def list_len(obj, keys):
    for key in keys:
        value = obj.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def validate_regression():
    before = sql_request_count()
    print(f"REGRESSION_AI_REQUESTS_BEFORE={before}", flush=True)

    port = 8011
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        wait_health(port, process)
        print("TEMP_PATCHED_FASTAPI=PASS PORT=8011", flush=True)

        print("REGRESSION_POSITIVE_ASK=START", flush=True)
        positive = call_ask(
            port,
            "What role does Azure Databricks play in TechScope? "
            "Include authoritative technology IDs and citations.",
        )
        print("REGRESSION_POSITIVE_ASK=PASS", flush=True)

        print("REGRESSION_NEGATIVE_ASK=START", flush=True)
        negative = call_ask(
            port,
            "포유류의 대표적인 동물은 뭐가있어?",
        )
        print("REGRESSION_NEGATIVE_ASK=PASS", flush=True)

    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    after = sql_request_count()
    print(f"REGRESSION_AI_REQUESTS_AFTER={after}", flush=True)

    pos_grounded = positive.get("grounded") is True
    pos_citations = list_len(positive, ["citations"])
    pos_ids = list_len(
        positive,
        [
            "grounded_technology_ids",
            "groundedTechnologyIds",
            "technology_ids",
            "technologyIds",
            "grounded_technologies",
        ],
    )

    neg_grounded = negative.get("grounded") is False
    neg_citations = list_len(negative, ["citations"])
    neg_ids = list_len(
        negative,
        [
            "grounded_technology_ids",
            "groundedTechnologyIds",
            "technology_ids",
            "technologyIds",
            "grounded_technologies",
        ],
    )

    guard = negative.get("grounding_guard") or {}
    persistence = (
        negative.get("grounding_persistence_reconciliation") or {}
    )

    print(
        f"POSITIVE_GROUNDED={'PASS' if pos_grounded else 'FAIL'}",
        flush=True,
    )
    print(f"POSITIVE_CITATIONS={pos_citations}", flush=True)
    print(f"POSITIVE_TECHNOLOGY_IDS={pos_ids}", flush=True)

    print(
        f"NEGATIVE_GROUNDED_FALSE={'PASS' if neg_grounded else 'FAIL'}",
        flush=True,
    )
    print(f"NEGATIVE_CITATIONS={neg_citations}", flush=True)
    print(f"NEGATIVE_TECHNOLOGY_IDS={neg_ids}", flush=True)
    print(
        f"NEGATIVE_GUARD_STATUS={guard.get('status')}",
        flush=True,
    )
    print(
        "NEGATIVE_SQL_RECONCILIATION="
        + (
            "ATTEMPTED"
            if persistence.get("attempted")
            else "NOT_AVAILABLE"
        ),
        flush=True,
    )

    if after - before != 2:
        raise RuntimeError(
            f"AI_REQUEST_DELTA_MISMATCH expected=2 actual={after-before}"
        )

    if not pos_grounded or pos_citations <= 0 or pos_ids <= 0:
        raise RuntimeError(
            "POSITIVE_REGRESSION_FAIL: grounded/citations/technology IDs"
        )

    if not neg_grounded or neg_citations != 0 or neg_ids != 0:
        raise RuntimeError(
            "NEGATIVE_REGRESSION_FAIL: expected "
            "Grounded=False Citations=0 TechnologyIds=0"
        )

    if guard.get("status") != "BLOCKED_OUT_OF_DOMAIN":
        raise RuntimeError("NEGATIVE_GROUNDING_GUARD_NOT_TRIGGERED")

    print("AI_REQUEST_DELTA=PASS +2", flush=True)
    print("GROUNDING_POSITIVE_REGRESSION=PASS", flush=True)
    print("GROUNDING_NEGATIVE_REGRESSION=PASS", flush=True)

    return {
        "before": before,
        "after": after,
        "positive": {
            "grounded": pos_grounded,
            "citations": pos_citations,
            "technology_ids": pos_ids,
        },
        "negative": {
            "grounded": neg_grounded,
            "citations": neg_citations,
            "technology_ids": neg_ids,
            "guard": guard,
            "sql_reconciliation": persistence,
        },
    }


def detect_live_reload():
    cp = run(
        ["sh", "-lc", "ps -eo args | grep '[u]vicorn' || true"],
        check=False,
        timeout=30,
    )
    text = cp.stdout or ""
    reload_enabled = "--reload" in text
    print(
        f"LIVE_FASTAPI_AUTO_RELOAD={'YES' if reload_enabled else 'NO'}",
        flush=True,
    )
    print(
        f"LIVE_8000_RESTART_REQUIRED={'NO' if reload_enabled else 'YES'}",
        flush=True,
    )
    return reload_enabled


def main():
    now = datetime.now(timezone.utc).isoformat()

    print("GROUNDING_FALSE_POSITIVE_FIX_V1=START", flush=True)
    print("AZURE_RESOURCE_CREATION=NO", flush=True)
    print("AZURE_RESOURCE_DELETION=NO", flush=True)
    print("REAL_AI_ASK_CALLS=2", flush=True)

    calibration = calibrate()
    install(calibration)
    compile_and_lint()
    regression = validate_regression()
    reload_enabled = detect_live_reload()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "timestamp_utc": now,
                "status": "PASS",
                "search_service": SEARCH_SERVICE,
                "search_index": SEARCH_INDEX,
                "api_version": API_VERSION,
                "calibration": calibration,
                "regression": regression,
                "real_ai_ask_calls": 2,
                "live_auto_reload": reload_enabled,
                "live_restart_required": not reload_enabled,
                "search_key_persisted": False,
                "azure_resource_creation": False,
                "azure_resource_deletion": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("SEARCH_KEY_PERSISTED=NO", flush=True)
    print("GROUNDING_FALSE_POSITIVE_FIX_V1=PASS", flush=True)
    print(
        "REPORT=results/latest/grounding-false-positive-fix.json",
        flush=True,
    )

    if reload_enabled:
        print("NEXT_ACTION=LIVE_8000_REGRESSION_VERIFY", flush=True)
    else:
        print("NEXT_ACTION=SAFE_LIVE_FASTAPI_RESTART", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
