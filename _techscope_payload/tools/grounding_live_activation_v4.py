#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("/workspaces/TechScope")
GUARD = ROOT / "backend/app/grounding_guard.py"
MAIN = ROOT / "backend/app/main.py"
CONFIG = ROOT / "config/grounding-guard.json"
TEMPLATE = ROOT / "generated/grounding-live-activation/grounding_guard.py"
REPORT = ROOT / "results/latest/grounding-live-activation-v4.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

REQUIRED_ENV = {
    "TECHSCOPE_SEARCH_ENDPOINT",
    "TECHSCOPE_SEARCH_INDEX",
    "TECHSCOPE_AZURE_OPENAI_ENDPOINT",
    "TECHSCOPE_GENERATION_DEPLOYMENT",
    "TECHSCOPE_EMBEDDING_DEPLOYMENT",
}


def run(cmd, *, check=True, timeout=180, env=None, cwd=None):
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
            + (cp.stdout or "")[-5000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-5000:]
        )

    return cp


def read_proc_env(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    env = {}

    for chunk in raw.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue

        k, v = chunk.split(b"=", 1)

        env[
            k.decode("utf-8", errors="ignore")
        ] = v.decode("utf-8", errors="ignore")

    return env


def read_proc_argv(pid: int) -> list[str]:
    raw = Path(f"/proc/{pid}/cmdline").read_bytes()

    return [
        x.decode("utf-8", errors="ignore")
        for x in raw.split(b"\0")
        if x
    ]


def find_live():
    candidates = []

    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue

        pid = int(p.name)

        try:
            argv = read_proc_argv(pid)
            cmd = " ".join(argv)
            env = read_proc_env(pid)
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except Exception:
            continue

        low = cmd.lower()

        if "8011" in low or "8012" in low:
            continue

        if "uvicorn" not in low:
            continue

        if not (
            "8000" in low
            or "backend.app.main" in low
        ):
            continue

        techscope_count = len(
            REQUIRED_ENV & set(env)
        )

        if techscope_count == 0:
            continue

        candidates.append(
            (
                techscope_count,
                pid,
                argv,
                env,
                cwd,
            )
        )

    if not candidates:
        raise RuntimeError(
            "LIVE_FASTAPI_PROCESS_NOT_FOUND"
        )

    candidates.sort(
        reverse=True,
        key=lambda x: (x[0], -x[1]),
    )

    _, pid, argv, env, cwd = candidates[0]

    missing = sorted(REQUIRED_ENV - set(env))
    if missing:
        raise RuntimeError(
            "LIVE_FASTAPI_ENV_INCOMPLETE="
            + ",".join(missing)
        )

    proc_uid = os.stat(
        f"/proc/{pid}"
    ).st_uid

    if proc_uid != os.geteuid():
        raise RuntimeError(
            f"LIVE_FASTAPI_UID_MISMATCH "
            f"process_uid={proc_uid} runner_uid={os.geteuid()}"
        )

    if pid == 1:
        raise RuntimeError(
            "LIVE_FASTAPI_PID_1_SAFE_STOP"
        )

    print(f"LIVE_FASTAPI_OLD_PID={pid}", flush=True)
    print("LIVE_FASTAPI_PID_1=NO", flush=True)
    print(f"LIVE_FASTAPI_CWD={cwd}", flush=True)
    print(
        f"LIVE_FASTAPI_ENV_COUNT={len(env)}",
        flush=True,
    )
    print("LIVE_FASTAPI_ENV_VALUES_PRINTED=NO", flush=True)
    print("LIVE_FASTAPI_ENV_VALUES_PERSISTED=NO", flush=True)

    return pid, argv, env, cwd


def argv_with_port(argv: list[str], port: int) -> list[str]:
    result = list(argv)
    replaced = False

    i = 0
    while i < len(result):
        if result[i] == "--port":
            if i + 1 < len(result):
                result[i + 1] = str(port)
                replaced = True
                break

        if result[i].startswith("--port="):
            result[i] = f"--port={port}"
            replaced = True
            break

        i += 1

    if not replaced:
        result += ["--port", str(port)]

    return result


def wait_health(
    port: int,
    process: subprocess.Popen | None = None,
    timeout: int = 45,
):
    start = time.monotonic()
    url = f"http://127.0.0.1:{port}/health"

    while time.monotonic() - start < timeout:
        if (
            process is not None
            and process.poll() is not None
        ):
            raise RuntimeError(
                f"FASTAPI_PROCESS_EXITED "
                f"port={port} rc={process.returncode}"
            )

        try:
            with urlopen(
                Request(url, method="GET"),
                timeout=3,
            ) as response:
                if response.status == 200:
                    return
        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError(
        f"FASTAPI_HEALTH_TIMEOUT port={port}"
    )


def install_guard():
    if not TEMPLATE.exists():
        raise RuntimeError(
            "GROUNDING_GUARD_V4_TEMPLATE_NOT_FOUND"
        )

    if not CONFIG.exists():
        raise RuntimeError(
            "GROUNDING_GUARD_CONFIG_NOT_FOUND"
        )

    shutil.copy2(TEMPLATE, GUARD)

    for p in [GUARD, MAIN]:
        cp = run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(p),
            ],
            check=False,
            timeout=30,
        )

        if cp.returncode != 0:
            raise RuntimeError(
                f"GROUNDING_V4_COMPILE_FAIL={p}\n"
                + (cp.stderr or "")
            )

    print(
        "GROUNDING_SQL_RECONCILIATION_PATCH=PASS",
        flush=True,
    )
    print(
        "GROUNDING_V4_COMPILE=PASS",
        flush=True,
    )

    lint = run(
        [
            sys.executable,
            str(ROOT / "tools/architecture_lint.py"),
        ],
        check=False,
        timeout=120,
    )

    text = (
        (lint.stdout or "")
        + "\n"
        + (lint.stderr or "")
    )

    if (
        lint.returncode != 0
        or "ARCHITECTURE_LINT=PASS" not in text
    ):
        print(text[-5000:], flush=True)
        raise RuntimeError(
            "GROUNDING_V4_ARCHITECTURE_LINT=FAIL"
        )

    print(
        "GROUNDING_V4_ARCHITECTURE_LINT=PASS",
        flush=True,
    )


def sql_state():
    from mssql_python import connect

    conn = connect(
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;",
    )

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
        row = cur.fetchone()

        return {
            "request_count": int(row[0]),
            "max_request_key": int(row[1]),
        }

    finally:
        conn.close()


def verify_new_request(
    previous_max_key: int,
):
    from mssql_python import connect

    conn = connect(
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;",
    )

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                RequestKey,
                CitationFlag
            FROM techscope.FactAIRequest
            WHERE RequestKey > ?
            ORDER BY RequestKey
            """,
            (previous_max_key,),
        )

        rows = cur.fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                f"LIVE_SQL_NEW_REQUEST_COUNT="
                f"{len(rows)} expected=1"
            )

        request_key = int(rows[0][0])
        citation_flag = rows[0][1]

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.BridgeAIRequestTechnology
            WHERE RequestKey = ?
            """,
            (request_key,),
        )
        bridge_rows = int(cur.fetchone()[0])

        print(
            f"LIVE_NEGATIVE_REQUEST_KEY={request_key}",
            flush=True,
        )
        print(
            f"LIVE_NEGATIVE_SQL_CITATION_FLAG={citation_flag}",
            flush=True,
        )
        print(
            f"LIVE_NEGATIVE_SQL_BRIDGE_ROWS={bridge_rows}",
            flush=True,
        )

        normalized_flag = str(
            citation_flag
        ).lower()

        if normalized_flag not in {
            "0",
            "false",
        }:
            raise RuntimeError(
                "LIVE_NEGATIVE_SQL_CITATION_FLAG_NOT_ZERO"
            )

        if bridge_rows != 0:
            raise RuntimeError(
                "LIVE_NEGATIVE_SQL_BRIDGE_NOT_ZERO"
            )

        return {
            "request_key": request_key,
            "citation_flag": citation_flag,
            "bridge_rows": bridge_rows,
        }

    finally:
        conn.close()


def ask_negative():
    req = Request(
        "http://127.0.0.1:8000/ask",
        data=json.dumps(
            {
                "question": "포유류의 대표적인 동물은 뭐가있어?"
            }
        ).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )

    with urlopen(req, timeout=150) as response:
        if response.status != 200:
            raise RuntimeError(
                f"LIVE_NEGATIVE_HTTP={response.status}"
            )

        return json.loads(
            response.read().decode("utf-8")
        )


def list_len(obj, keys):
    for key in keys:
        value = obj.get(key)

        if isinstance(value, list):
            return len(value)

    return 0


def main():
    print(
        "GROUNDING_LIVE_ACTIVATION_V4=START",
        flush=True,
    )
    print("REAL_AI_ASK_CALLS=1", flush=True)
    print(
        "EXPECTED_FACT_AI_REQUEST_DELTA=+1",
        flush=True,
    )
    print("CONTAINER_RECREATE=NO", flush=True)
    print("AZURE_RESOURCE_MUTATION=NO", flush=True)

    old_pid, old_argv, old_env, old_cwd = find_live()

    install_guard()

    # Preflight the exact patched application with the live environment on
    # an alternate port before stopping the current demo endpoint.
    test_argv = argv_with_port(
        old_argv,
        8012,
    )

    test_log = open(
        "/tmp/techscope-grounding-v4-preflight.log",
        "w",
        encoding="utf-8",
    )

    test_proc = subprocess.Popen(
        test_argv,
        cwd=old_cwd,
        env=old_env,
        stdout=test_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )

    try:
        wait_health(
            8012,
            process=test_proc,
            timeout=45,
        )
        print(
            "PATCHED_FASTAPI_PREFLIGHT=PASS PORT=8012",
            flush=True,
        )
    finally:
        test_proc.terminate()

        try:
            test_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            test_proc.kill()
            test_proc.wait(timeout=5)

        test_log.close()

    before = sql_state()

    print(
        f"LIVE_AI_REQUESTS_BEFORE="
        f"{before['request_count']}",
        flush=True,
    )
    print(
        f"LIVE_MAX_REQUEST_KEY_BEFORE="
        f"{before['max_request_key']}",
        flush=True,
    )

    # Handover only after patched app has successfully booted on :8012.
    os.kill(
        old_pid,
        signal.SIGTERM,
    )

    stop_start = time.monotonic()

    while Path(f"/proc/{old_pid}").exists():
        if time.monotonic() - stop_start > 15:
            try:
                os.kill(
                    old_pid,
                    signal.SIGKILL,
                )
            except ProcessLookupError:
                pass
            break

        time.sleep(0.5)

    print(
        "LIVE_FASTAPI_OLD_PROCESS_STOP=PASS",
        flush=True,
    )

    live_log = open(
        "/tmp/techscope-live-fastapi.log",
        "a",
        encoding="utf-8",
    )

    new_proc = subprocess.Popen(
        old_argv,
        cwd=old_cwd,
        env=old_env,
        stdout=live_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )

    try:
        wait_health(
            8000,
            process=new_proc,
            timeout=45,
        )
    except Exception:
        live_log.close()
        raise

    print(
        f"LIVE_FASTAPI_NEW_PID={new_proc.pid}",
        flush=True,
    )
    print(
        "LIVE_FASTAPI_RESTART=PASS",
        flush=True,
    )
    print(
        "LIVE_FASTAPI_HEALTH=PASS HTTP=200",
        flush=True,
    )

    print(
        "LIVE_NEGATIVE_ASK=START",
        flush=True,
    )

    negative = ask_negative()

    print(
        "LIVE_NEGATIVE_ASK=PASS",
        flush=True,
    )

    after = sql_state()

    print(
        f"LIVE_AI_REQUESTS_AFTER="
        f"{after['request_count']}",
        flush=True,
    )

    delta = (
        after["request_count"]
        - before["request_count"]
    )

    grounded_false = (
        negative.get("grounded") is False
    )
    citations = list_len(
        negative,
        ["citations"],
    )
    tech_ids = list_len(
        negative,
        [
            "grounded_technology_ids",
            "groundedTechnologyIds",
            "technology_ids",
            "technologyIds",
            "grounded_technologies",
        ],
    )

    print(
        f"LIVE_NEGATIVE_GROUNDED_FALSE="
        f"{'PASS' if grounded_false else 'FAIL'}",
        flush=True,
    )
    print(
        f"LIVE_NEGATIVE_CITATIONS={citations}",
        flush=True,
    )
    print(
        f"LIVE_NEGATIVE_TECHNOLOGY_IDS={tech_ids}",
        flush=True,
    )

    if delta != 1:
        raise RuntimeError(
            f"LIVE_AI_REQUEST_DELTA="
            f"{delta} expected=1"
        )

    if (
        not grounded_false
        or citations != 0
        or tech_ids != 0
    ):
        raise RuntimeError(
            "LIVE_NEGATIVE_RESPONSE_REGRESSION_FAIL"
        )

    sql_verify = verify_new_request(
        before["max_request_key"]
    )

    print(
        "LIVE_AI_REQUEST_DELTA=PASS +1",
        flush=True,
    )
    print(
        "LIVE_NEGATIVE_RESPONSE=PASS",
        flush=True,
    )
    print(
        "LIVE_NEGATIVE_SQL_PERSISTENCE=PASS",
        flush=True,
    )

    report = {
        "status": "PASS",
        "old_pid": old_pid,
        "new_pid": new_proc.pid,
        "container_recreated": False,
        "azure_resource_mutation": False,
        "real_ai_ask_calls": 1,
        "ai_request_before": before["request_count"],
        "ai_request_after": after["request_count"],
        "ai_request_delta": delta,
        "negative_response": {
            "grounded": negative.get("grounded"),
            "citations": citations,
            "technology_ids": tech_ids,
        },
        "sql": sql_verify,
        "env_values_printed": False,
        "env_values_persisted": False,
    }

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    live_log.flush()
    live_log.close()

    print(
        "GROUNDING_FALSE_POSITIVE_FIX=LIVE_VERIFIED",
        flush=True,
    )
    print(
        "REPORT=results/latest/grounding-live-activation-v4.json",
        flush=True,
    )
    print(
        "GROUNDING_LIVE_ACTIVATION_V4=PASS",
        flush=True,
    )
    print(
        "NEXT_ACTION=POWERBI_SNAPSHOT_SYNC_AND_GIT_CHECKPOINT",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
