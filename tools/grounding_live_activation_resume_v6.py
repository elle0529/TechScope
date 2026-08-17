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
TEMPLATE = ROOT / "generated/grounding-live-v6/grounding_guard.py"
REPORT = ROOT / "results/latest/grounding-live-activation-v6.json"

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


def proc_cmd(pid: int) -> str:
    raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    return " ".join(
        x.decode("utf-8", errors="ignore")
        for x in raw.split(b"\0")
        if x
    )


def proc_env(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    env = {}

    for chunk in raw.split(b"\0"):
        if b"=" not in chunk:
            continue
        k, v = chunk.split(b"=", 1)
        env[
            k.decode("utf-8", errors="ignore")
        ] = v.decode("utf-8", errors="ignore")

    return env


def uvicorn_processes():
    rows = []

    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue

        pid = int(p.name)

        try:
            cmd = proc_cmd(pid)
            env = proc_env(pid)
            cwd = os.readlink(f"/proc/{pid}/cwd")
            uid = os.stat(f"/proc/{pid}").st_uid
        except Exception:
            continue

        low = cmd.lower()
        if "uvicorn" not in low:
            continue
        if "backend.app.main" not in low:
            continue

        port = None
        tokens = cmd.split()

        for i, token in enumerate(tokens):
            if token == "--port" and i + 1 < len(tokens):
                try:
                    port = int(tokens[i + 1])
                except Exception:
                    pass
            elif token.startswith("--port="):
                try:
                    port = int(token.split("=", 1)[1])
                except Exception:
                    pass

        if port is None:
            port = 8000

        rows.append(
            {
                "pid": pid,
                "cmd": cmd,
                "env": env,
                "cwd": cwd,
                "uid": uid,
                "port": port,
            }
        )

    return rows


def live_context():
    candidates = []

    for row in uvicorn_processes():
        if row["port"] != 8000:
            continue
        score = len(REQUIRED_ENV & set(row["env"]))
        if score:
            candidates.append((score, row))

    if not candidates:
        raise RuntimeError("LIVE_FASTAPI_CONTEXT_NOT_FOUND")

    candidates.sort(
        reverse=True,
        key=lambda x: (x[0], -x[1]["pid"]),
    )

    _, row = candidates[0]

    missing = sorted(
        REQUIRED_ENV - set(row["env"])
    )
    if missing:
        raise RuntimeError(
            "LIVE_FASTAPI_ENV_INCOMPLETE="
            + ",".join(missing)
        )

    if row["uid"] != os.geteuid():
        raise RuntimeError(
            "LIVE_FASTAPI_UID_MISMATCH"
        )

    print(
        f"LIVE_CONTEXT_SOURCE_PID={row['pid']}",
        flush=True,
    )
    print(
        f"LIVE_FASTAPI_CWD={row['cwd']}",
        flush=True,
    )
    print("LIVE_ENV_VALUES_PRINTED=NO", flush=True)
    print("LIVE_ENV_VALUES_PERSISTED=NO", flush=True)

    return row["env"], row["cwd"]


def install_v6_guard():
    if not TEMPLATE.exists():
        raise RuntimeError("GROUNDING_V6_TEMPLATE_NOT_FOUND")

    if not CONFIG.exists():
        raise RuntimeError("GROUNDING_CONFIG_NOT_FOUND")

    shutil.copy2(TEMPLATE, GUARD)

    for path in [GUARD, MAIN]:
        cp = run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(path),
            ],
            check=False,
            timeout=30,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"GROUNDING_V6_COMPILE_FAIL={path}\n"
                + (cp.stderr or "")
            )

    print("GROUNDING_V6_SOURCE=PASS", flush=True)
    print("GROUNDING_V6_COMPILE=PASS", flush=True)

    lint = run(
        [
            sys.executable,
            str(ROOT / "tools/architecture_lint.py"),
        ],
        check=False,
        timeout=120,
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")

    if (
        lint.returncode != 0
        or "ARCHITECTURE_LINT=PASS" not in text
    ):
        print(text[-5000:], flush=True)
        raise RuntimeError(
            "GROUNDING_V6_ARCHITECTURE_LINT=FAIL"
        )

    print(
        "GROUNDING_V6_ARCHITECTURE_LINT=PASS",
        flush=True,
    )


def start_uvicorn(
    port: int,
    host: str,
    env: dict[str, str],
    cwd: str,
    log_path: str,
):
    log = open(
        log_path,
        "a",
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )

    return proc, log


def get_json(url: str, timeout=5):
    with urlopen(
        Request(url, method="GET"),
        timeout=timeout,
    ) as response:
        return (
            response.status,
            json.loads(
                response.read().decode("utf-8")
            ),
        )


def wait_identity(
    port: int,
    expected_pid: int,
    process: subprocess.Popen,
    timeout: int = 60,
):
    start = time.monotonic()
    marker_url = (
        f"http://127.0.0.1:{port}/demo/grounding-runtime"
    )

    while time.monotonic() - start < timeout:
        if process.poll() is not None:
            raise RuntimeError(
                f"FASTAPI_PROCESS_EXITED "
                f"port={port} rc={process.returncode}"
            )

        try:
            status, marker = get_json(
                marker_url,
                timeout=3,
            )

            if (
                status == 200
                and marker.get("version") == "v6"
                and int(marker.get("pid")) == expected_pid
                and marker.get("ask_guard_wrapped") is True
            ):
                # Stabilization: prevent a stale listener race from
                # satisfying only the first request.
                time.sleep(2)

                if process.poll() is not None:
                    raise RuntimeError(
                        f"FASTAPI_PROCESS_EXITED_AFTER_MARKER "
                        f"port={port}"
                    )

                status2, marker2 = get_json(
                    marker_url,
                    timeout=3,
                )

                if (
                    status2 == 200
                    and marker2 == marker
                ):
                    return marker

        except Exception:
            pass

        time.sleep(1)

    raise RuntimeError(
        f"FASTAPI_IDENTITY_TIMEOUT "
        f"port={port} expected_pid={expected_pid}"
    )


def http_8000_available() -> bool:
    try:
        with urlopen(
            Request(
                "http://127.0.0.1:8000/health",
                method="GET",
            ),
            timeout=2,
        ) as response:
            return response.status == 200
    except Exception:
        return False


def stop_all_live_8000():
    deadline = time.monotonic() + 20
    stopped = set()

    while time.monotonic() < deadline:
        current = [
            row
            for row in uvicorn_processes()
            if row["port"] == 8000
            and row["uid"] == os.geteuid()
        ]

        if not current:
            if not http_8000_available():
                print(
                    f"LIVE_8000_STOPPED_PIDS="
                    f"{','.join(map(str, sorted(stopped))) or 'NONE'}",
                    flush=True,
                )
                print(
                    "LIVE_8000_NO_LISTENER=PASS",
                    flush=True,
                )
                return stopped

        for row in current:
            pid = row["pid"]
            if pid == 1:
                raise RuntimeError(
                    "LIVE_8000_PID_1_SAFE_STOP"
                )

            if pid not in stopped:
                try:
                    os.kill(pid, signal.SIGTERM)
                    stopped.add(pid)
                except ProcessLookupError:
                    pass

        time.sleep(1)

    # Escalate only matching Uvicorn processes, never arbitrary PIDs.
    current = [
        row
        for row in uvicorn_processes()
        if row["port"] == 8000
        and row["uid"] == os.geteuid()
        and row["pid"] != 1
    ]

    for row in current:
        try:
            os.kill(row["pid"], signal.SIGKILL)
            stopped.add(row["pid"])
        except ProcessLookupError:
            pass

    time.sleep(2)

    if http_8000_available():
        diagnostics = run(
            [
                "sh",
                "-lc",
                "ss -ltnp 2>/dev/null | grep ':8000' || true",
            ],
            check=False,
            timeout=10,
        )
        print(
            "LIVE_8000_LISTENER_DIAGNOSTIC="
            + (diagnostics.stdout or "").strip(),
            flush=True,
        )
        raise RuntimeError(
            "LIVE_8000_STALE_LISTENER_REMAINS"
        )

    print(
        f"LIVE_8000_STOPPED_PIDS="
        f"{','.join(map(str, sorted(stopped))) or 'NONE'}",
        flush=True,
    )
    print("LIVE_8000_NO_LISTENER=PASS", flush=True)

    return stopped


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
            SELECT COUNT_BIG(*), COALESCE(MAX(RequestKey), 0)
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


def ask_negative():
    req = Request(
        "http://127.0.0.1:8000/ask",
        data=json.dumps(
            {
                "question": "포유류의 대표적인 동물은 뭐가있어?"
            }
        ).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urlopen(req, timeout=150) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def list_len(obj, keys):
    for key in keys:
        value = obj.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def verify_sql(previous_max_key: int):
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
            SELECT RequestKey, CitationFlag
            FROM techscope.FactAIRequest
            WHERE RequestKey > ?
            ORDER BY RequestKey
            """,
            (previous_max_key,),
        )
        rows = cur.fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                f"LIVE_SQL_NEW_REQUEST_COUNT={len(rows)} expected=1"
            )

        key = int(rows[0][0])
        citation_flag = rows[0][1]

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.BridgeAIRequestTechnology
            WHERE RequestKey = ?
            """,
            (key,),
        )
        bridge = int(cur.fetchone()[0])

        print(
            f"LIVE_NEGATIVE_REQUEST_KEY={key}",
            flush=True,
        )
        print(
            f"LIVE_NEGATIVE_SQL_CITATION_FLAG={citation_flag}",
            flush=True,
        )
        print(
            f"LIVE_NEGATIVE_SQL_BRIDGE_ROWS={bridge}",
            flush=True,
        )

        if str(citation_flag).lower() not in {"0", "false"}:
            raise RuntimeError(
                "LIVE_NEGATIVE_SQL_CITATION_FLAG_NOT_ZERO"
            )

        if bridge != 0:
            raise RuntimeError(
                "LIVE_NEGATIVE_SQL_BRIDGE_NOT_ZERO"
            )

        return {
            "request_key": key,
            "citation_flag": citation_flag,
            "bridge_rows": bridge,
        }

    finally:
        conn.close()


def main():
    print(
        "GROUNDING_LIVE_ACTIVATION_RESUME_V6=START",
        flush=True,
    )
    print("REAL_AI_ASK_CALLS=1", flush=True)
    print(
        "EXPECTED_FACT_AI_REQUEST_DELTA=+1",
        flush=True,
    )
    print("CONTAINER_RECREATE=NO", flush=True)
    print("AZURE_RESOURCE_MUTATION=NO", flush=True)

    env, cwd = live_context()
    install_v6_guard()

    # 1. Prove the patched app itself is v6 on a private port.
    test_proc, test_log = start_uvicorn(
        8012,
        "127.0.0.1",
        env,
        cwd,
        "/tmp/techscope-grounding-v6-preflight.log",
    )

    try:
        marker = wait_identity(
            8012,
            test_proc.pid,
            test_proc,
            timeout=60,
        )
        print(
            f"PATCHED_PREFLIGHT_RUNTIME_VERSION={marker['version']}",
            flush=True,
        )
        print(
            f"PATCHED_PREFLIGHT_PID_MATCH=PASS PID={test_proc.pid}",
            flush=True,
        )
        print(
            "PATCHED_PREFLIGHT_ASK_GUARD_WRAPPED=PASS",
            flush=True,
        )
    except Exception:
        try:
            test_log.flush()
            content = Path(
                "/tmp/techscope-grounding-v6-preflight.log"
            ).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            print(
                "----- V6 PREFLIGHT LOG TAIL START -----",
                flush=True,
            )
            print(content[-5000:], flush=True)
            print(
                "----- V6 PREFLIGHT LOG TAIL END -----",
                flush=True,
            )
        except Exception:
            pass
        raise
    finally:
        if test_proc.poll() is None:
            test_proc.terminate()
            try:
                test_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                test_proc.kill()
                test_proc.wait(timeout=5)
        test_log.close()

    before = sql_state()

    print(
        f"LIVE_AI_REQUESTS_BEFORE={before['request_count']}",
        flush=True,
    )
    print(
        f"LIVE_MAX_REQUEST_KEY_BEFORE={before['max_request_key']}",
        flush=True,
    )

    # 2. Remove every same-UID TechScope Uvicorn listener on :8000 and
    # prove there is no listener before starting the replacement.
    stopped = stop_all_live_8000()

    # 3. Start exactly one v6 live process.
    live_proc, live_log = start_uvicorn(
        8000,
        "0.0.0.0",
        env,
        cwd,
        "/tmp/techscope-live-fastapi-v6.log",
    )

    try:
        live_marker = wait_identity(
            8000,
            live_proc.pid,
            live_proc,
            timeout=60,
        )
    except Exception:
        try:
            live_log.flush()
            content = Path(
                "/tmp/techscope-live-fastapi-v6.log"
            ).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            print(
                "----- V6 LIVE LOG TAIL START -----",
                flush=True,
            )
            print(content[-5000:], flush=True)
            print(
                "----- V6 LIVE LOG TAIL END -----",
                flush=True,
            )
        except Exception:
            pass
        raise

    print(
        f"LIVE_RUNTIME_VERSION={live_marker['version']}",
        flush=True,
    )
    print(
        f"LIVE_FASTAPI_NEW_PID={live_proc.pid}",
        flush=True,
    )
    print(
        "LIVE_RUNTIME_PID_MATCH=PASS",
        flush=True,
    )
    print(
        "LIVE_ASK_GUARD_WRAPPED=PASS",
        flush=True,
    )
    print(
        "LIVE_FASTAPI_HEALTH_AND_IDENTITY=PASS",
        flush=True,
    )

    # 4. Only now spend one real model request.
    print("LIVE_NEGATIVE_ASK=START", flush=True)
    negative = ask_negative()
    print("LIVE_NEGATIVE_ASK=PASS", flush=True)

    after = sql_state()
    delta = after["request_count"] - before["request_count"]

    grounded_false = negative.get("grounded") is False
    citations = list_len(negative, ["citations"])
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
        f"LIVE_AI_REQUESTS_AFTER={after['request_count']}",
        flush=True,
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
            f"LIVE_AI_REQUEST_DELTA={delta} expected=1"
        )

    if not grounded_false or citations != 0 or tech_ids != 0:
        raise RuntimeError(
            "LIVE_NEGATIVE_RESPONSE_REGRESSION_FAIL"
        )

    sql_verify = verify_sql(
        before["max_request_key"]
    )

    print("LIVE_AI_REQUEST_DELTA=PASS +1", flush=True)
    print("LIVE_NEGATIVE_RESPONSE=PASS", flush=True)
    print(
        "LIVE_NEGATIVE_SQL_PERSISTENCE=PASS",
        flush=True,
    )

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime_version": "v6",
                "stopped_live_pids": sorted(stopped),
                "new_live_pid": live_proc.pid,
                "live_pid_identity_verified": True,
                "ask_guard_wrapped": True,
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
                "environment_values_printed": False,
                "environment_values_persisted": False,
            },
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
        "REPORT=results/latest/grounding-live-activation-v6.json",
        flush=True,
    )
    print(
        "GROUNDING_LIVE_ACTIVATION_RESUME_V6=PASS",
        flush=True,
    )
    print(
        "NEXT_ACTION=POWERBI_SNAPSHOT_SYNC_AND_GIT_CHECKPOINT",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
