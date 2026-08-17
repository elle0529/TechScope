#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/workspaces/TechScope")
MAIN = ROOT / "backend/app/main.py"
GUARD = ROOT / "backend/app/grounding_guard.py"
CONFIG = ROOT / "config/grounding-guard.json"
REPORT = ROOT / "results/latest/grounding-false-positive-fix.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

REQUIRED = {
    "TECHSCOPE_SEARCH_ENDPOINT",
    "TECHSCOPE_SEARCH_INDEX",
    "TECHSCOPE_AZURE_OPENAI_ENDPOINT",
    "TECHSCOPE_GENERATION_DEPLOYMENT",
    "TECHSCOPE_EMBEDDING_DEPLOYMENT",
}


def run(cmd, *, check=True, timeout=180, cwd=None, env=None):
    cp = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        env=env,
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


def verify_installed_guard():
    for p in [MAIN, GUARD, CONFIG]:
        if not p.exists():
            raise RuntimeError(f"GROUNDING_RESUME_REQUIRED_FILE_MISSING={p}")

    main_text = MAIN.read_text(encoding="utf-8")
    if "install_grounding_guard" not in main_text:
        raise RuntimeError("GROUNDING_GUARD_WIRING_MISSING")

    for p in [MAIN, GUARD]:
        cp = run(
            [sys.executable, "-m", "py_compile", str(p)],
            check=False,
            timeout=30,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"GROUNDING_RESUME_COMPILE_FAIL={p}\n{cp.stderr}"
            )

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    threshold = float(cfg.get("threshold") or 0)
    if threshold <= 0:
        raise RuntimeError("GROUNDING_THRESHOLD_MISSING_OR_INVALID")

    print("GROUNDING_GUARD_EXISTING_SOURCE=PASS", flush=True)
    print("GROUNDING_GUARD_EXISTING_CONFIG=PASS", flush=True)
    print(f"GROUNDING_THRESHOLD={threshold:.6f}", flush=True)

    lint = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=120,
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")
    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError("GROUNDING_RESUME_ARCHITECTURE_LINT=FAIL")

    print("GROUNDING_RESUME_ARCHITECTURE_LINT=PASS", flush=True)


def _read_proc_env(pid: str) -> dict[str, str]:
    data = Path(f"/proc/{pid}/environ").read_bytes()
    result = {}
    for chunk in data.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        key_b, value_b = chunk.split(b"=", 1)
        key = key_b.decode("utf-8", errors="ignore")
        value = value_b.decode("utf-8", errors="ignore")
        result[key] = value
    return result


def discover_live_env():
    candidates = []

    proc = Path("/proc")
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue

        try:
            cmdline = (p / "cmdline").read_bytes().replace(b"\0", b" ")
            cmd = cmdline.decode("utf-8", errors="ignore")
        except Exception:
            continue

        low = cmd.lower()
        if "8011" in low:
            continue

        is_fastapi = (
            "uvicorn" in low
            or "backend.app.main" in low
            or "backend/app/main.py" in low
        )
        is_live = "8000" in low or "uvicorn" in low

        if not (is_fastapi and is_live):
            continue

        try:
            env = _read_proc_env(p.name)
        except Exception:
            continue

        techscope = {
            k: v for k, v in env.items()
            if k.startswith("TECHSCOPE_")
        }
        present = REQUIRED & set(techscope)
        if present:
            candidates.append((len(present), int(p.name), techscope, cmd))

    if not candidates:
        raise RuntimeError(
            "LIVE_FASTAPI_ENV_DISCOVERY_FAIL: "
            "no readable live FastAPI process with TECHSCOPE_* variables"
        )

    candidates.sort(reverse=True, key=lambda x: (x[0], -x[1]))
    _, pid, techscope, _ = candidates[0]

    missing = sorted(REQUIRED - set(techscope))
    if missing:
        raise RuntimeError(
            "LIVE_FASTAPI_ENV_INCOMPLETE missing=" + ",".join(missing)
        )

    print(f"LIVE_FASTAPI_ENV_SOURCE=PASS PID={pid}", flush=True)
    print(
        f"LIVE_FASTAPI_TECHSCOPE_ENV_COUNT={len(techscope)}",
        flush=True,
    )
    print("LIVE_FASTAPI_ENV_VALUES_PRINTED=NO", flush=True)
    print("LIVE_FASTAPI_ENV_VALUES_PERSISTED=NO", flush=True)

    return techscope


def sql_counts():
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
        cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
        requests = int(cur.fetchone()[0])

        cur.execute(
            "SELECT COUNT_BIG(*) "
            "FROM techscope.BridgeAIRequestTechnology"
        )
        bridge = int(cur.fetchone()[0])

        return requests, bridge
    finally:
        conn.close()


def wait_health(port: int, process: subprocess.Popen):
    url = f"http://127.0.0.1:{port}/health"
    start = time.monotonic()

    while time.monotonic() - start < 60:
        if process.poll() is not None:
            out, err = process.communicate(timeout=5)
            raise RuntimeError(
                "TEMP_PATCHED_FASTAPI_EXITED\n"
                + (out or "")[-3000:]
                + "\n"
                + (err or "")[-5000:]
            )

        try:
            with urlopen(Request(url, method="GET"), timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError("TEMP_PATCHED_FASTAPI_HEALTH_TIMEOUT")


def ask(port: int, question: str) -> dict:
    req = Request(
        f"http://127.0.0.1:{port}/ask",
        data=json.dumps({"question": question}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=150) as r:
        if r.status != 200:
            raise RuntimeError(f"ASK_HTTP_STATUS={r.status}")
        return json.loads(r.read().decode("utf-8"))


def list_len(obj, keys):
    for key in keys:
        value = obj.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def regression(live_env):
    before_requests, before_bridge = sql_counts()

    print(
        f"REGRESSION_AI_REQUESTS_BEFORE={before_requests}",
        flush=True,
    )
    print(
        f"REGRESSION_BRIDGE_ROWS_BEFORE={before_bridge}",
        flush=True,
    )

    env = os.environ.copy()
    env.update(live_env)
    env["PYTHONPATH"] = str(ROOT)

    port = 8011
    proc = subprocess.Popen(
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
        wait_health(port, proc)
        print("TEMP_PATCHED_FASTAPI=PASS PORT=8011", flush=True)

        print("REGRESSION_POSITIVE_ASK=START", flush=True)
        positive = ask(
            port,
            "What role does Azure Databricks play in TechScope? "
            "Include authoritative technology IDs and citations.",
        )
        print("REGRESSION_POSITIVE_ASK=PASS", flush=True)

        print("REGRESSION_NEGATIVE_ASK=START", flush=True)
        negative = ask(
            port,
            "포유류의 대표적인 동물은 뭐가있어?",
        )
        print("REGRESSION_NEGATIVE_ASK=PASS", flush=True)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    after_requests, after_bridge = sql_counts()

    print(
        f"REGRESSION_AI_REQUESTS_AFTER={after_requests}",
        flush=True,
    )
    print(
        f"REGRESSION_BRIDGE_ROWS_AFTER={after_bridge}",
        flush=True,
    )

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

    delta = after_requests - before_requests

    if delta != 2:
        raise RuntimeError(
            f"AI_REQUEST_DELTA_MISMATCH expected=2 actual={delta}"
        )

    if not pos_grounded or pos_citations <= 0 or pos_ids <= 0:
        raise RuntimeError(
            "POSITIVE_REGRESSION_FAIL: "
            "expected Grounded=True, citations>0, technology IDs>0"
        )

    if not neg_grounded or neg_citations != 0 or neg_ids != 0:
        raise RuntimeError(
            "NEGATIVE_REGRESSION_FAIL: "
            "expected Grounded=False, citations=0, technology IDs=0"
        )

    if guard.get("status") != "BLOCKED_OUT_OF_DOMAIN":
        raise RuntimeError(
            "NEGATIVE_REGRESSION_FAIL: grounding guard not triggered"
        )

    print("AI_REQUEST_DELTA=PASS +2", flush=True)
    print("GROUNDING_POSITIVE_REGRESSION=PASS", flush=True)
    print("GROUNDING_NEGATIVE_REGRESSION=PASS", flush=True)

    return {
        "before_requests": before_requests,
        "after_requests": after_requests,
        "before_bridge": before_bridge,
        "after_bridge": after_bridge,
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
    print("GROUNDING_FALSE_POSITIVE_RESUME_V2=START", flush=True)
    print("REAL_AI_ASK_CALLS_THIS_RUN=2", flush=True)
    print("AZURE_RESOURCE_CREATION=NO", flush=True)
    print("AZURE_RESOURCE_DELETION=NO", flush=True)

    verify_installed_guard()
    live_env = discover_live_env()
    result = regression(live_env)
    reload_enabled = detect_live_reload()

    existing = {}
    if REPORT.exists():
        try:
            existing = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing.update(
        {
            "status": "PASS",
            "resume_version": "v2",
            "regression": result,
            "real_ai_ask_calls_completed": 2,
            "live_auto_reload": reload_enabled,
            "live_restart_required": not reload_enabled,
            "live_fastapi_env_reused_in_memory_only": True,
            "live_fastapi_env_values_persisted": False,
            "azure_resource_creation": False,
            "azure_resource_deletion": False,
        }
    )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("LIVE_FASTAPI_ENV_VALUES_PERSISTED=NO", flush=True)
    print("GROUNDING_FALSE_POSITIVE_RESUME_V2=PASS", flush=True)
    print(
        "REPORT=results/latest/grounding-false-positive-fix.json",
        flush=True,
    )

    if reload_enabled:
        print("NEXT_ACTION=LIVE_8000_FINAL_VERIFY", flush=True)
    else:
        print("NEXT_ACTION=SAFE_LIVE_FASTAPI_RESTART", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
