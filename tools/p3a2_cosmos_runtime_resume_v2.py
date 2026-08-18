#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path("/workspaces/TechScope")

RG = "rg-techscope-dev-239bd206"
SEARCH_SERVICE = "srch-techscope-dev-239bd206-b1"
SEARCH_INDEX = "techscope-chunks"
OPENAI_ACCOUNT = "aoai-techscope-dev-239bd206"
GENERATION_DEPLOYMENT = "techscope-gpt-4-1-mini"
EMBEDDING_DEPLOYMENT = "techscope-embedding-3-small"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

MAIN = ROOT / "backend/app/main.py"
STORE = ROOT / "backend/app/cosmos_interaction_store.py"
RUNTIME = ROOT / "backend/app/cosmos_runtime.py"
CONFIG = ROOT / "config/cosmos-runtime.json"
P3A1 = ROOT / "results/latest/p3a1-cosmos-provision.json"

RESULT = ROOT / "results/latest/p3a2-cosmos-runtime.json"
EVIDENCE = ROOT / "evidence/cosmos"
STATUS_DOC = ROOT / "docs/status.md"
EVIDENCE_DOC = ROOT / "docs/evidence.md"


def run(
    cmd,
    *,
    check=True,
    timeout=180,
    cwd=ROOT,
    env=None,
):
    cp = subprocess.run(
        cmd,
        cwd=cwd,
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


def az_tsv(args, timeout=90):
    cp = run(
        [
            "az",
            *args,
            "-o",
            "tsv",
            "--only-show-errors",
        ],
        timeout=timeout,
    )
    return (cp.stdout or "").strip()


def verify_installed_source():
    if not P3A1.exists():
        raise RuntimeError("P3A1_RESULT_MISSING")

    p3a1 = json.loads(
        P3A1.read_text(encoding="utf-8")
    )

    if p3a1.get("status") != "PASS":
        raise RuntimeError("P3A1_NOT_PASS")

    required = [
        MAIN,
        STORE,
        RUNTIME,
        CONFIG,
    ]

    for path in required:
        if not path.exists():
            raise RuntimeError(
                f"P3A2_SOURCE_MISSING={path}"
            )

    main_text = MAIN.read_text(encoding="utf-8")

    if "install_cosmos_runtime(app)" not in main_text:
        raise RuntimeError(
            "P3A2_MAIN_COSMOS_INSTALL_CALL_MISSING"
        )

    print("P3A1_COSMOS_FOUNDATION=PASS", flush=True)
    print("P3A2_INSTALLED_SOURCE=PASS", flush=True)

    return p3a1


def compile_and_lint(label):
    for path in [STORE, RUNTIME, MAIN]:
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
                f"PY_COMPILE_FAIL={path}\n"
                + (cp.stderr or "")
            )

    print(
        f"COSMOS_RUNTIME_COMPILE_{label}=PASS",
        flush=True,
    )

    cp = run(
        [
            sys.executable,
            str(ROOT / "tools/architecture_lint.py"),
        ],
        check=False,
        timeout=120,
    )

    text = (cp.stdout or "") + "\n" + (cp.stderr or "")

    if (
        cp.returncode != 0
        or "ARCHITECTURE_LINT=PASS" not in text
    ):
        print(text[-5000:], flush=True)
        raise RuntimeError(
            f"ARCHITECTURE_LINT_{label}=FAIL"
        )

    print(
        f"ARCHITECTURE_LINT_{label}=PASS",
        flush=True,
    )


def source_env_names():
    names = set()

    for path in (ROOT / "backend/app").glob("*.py"):
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except Exception:
            continue

        names.update(
            re.findall(
                r"\b(?:TECHSCOPE|AZURE|OPENAI)_[A-Z0-9_]+\b",
                text,
            )
        )

    return names


def build_runtime_env():
    print(
        "RUNTIME_ENV_RECOVERY=START",
        flush=True,
    )

    account = run(
        ["az", "account", "show", "-o", "none"],
        check=False,
        timeout=30,
    )

    if account.returncode != 0:
        raise RuntimeError(
            "AZURE_LOGIN_REQUIRED_FOR_RUNTIME_RECOVERY"
        )

    env = os.environ.copy()
    names = source_env_names()

    search_endpoint = (
        f"https://{SEARCH_SERVICE}.search.windows.net"
    )

    openai_endpoint = az_tsv(
        [
            "cognitiveservices",
            "account",
            "show",
            "--name",
            OPENAI_ACCOUNT,
            "--resource-group",
            RG,
            "--query",
            "properties.endpoint",
        ],
        timeout=60,
    )

    if not openai_endpoint:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT_RECOVERY_FAIL"
        )

    # These were the known required runtime settings in the existing app.
    env["TECHSCOPE_SEARCH_ENDPOINT"] = search_endpoint
    env["TECHSCOPE_SEARCH_INDEX"] = SEARCH_INDEX
    env["TECHSCOPE_AZURE_OPENAI_ENDPOINT"] = openai_endpoint
    env["TECHSCOPE_GENERATION_DEPLOYMENT"] = GENERATION_DEPLOYMENT
    env["TECHSCOPE_EMBEDDING_DEPLOYMENT"] = EMBEDDING_DEPLOYMENT

    # Recover keys in memory only when source code references a matching key var.
    search_key_vars = sorted(
        name
        for name in names
        if "SEARCH" in name and "KEY" in name
    )

    openai_key_vars = sorted(
        name
        for name in names
        if "OPENAI" in name and "KEY" in name
    )

    if search_key_vars:
        search_key = az_tsv(
            [
                "search",
                "admin-key",
                "show",
                "--service-name",
                SEARCH_SERVICE,
                "--resource-group",
                RG,
                "--query",
                "primaryKey",
            ],
            timeout=60,
        )

        if not search_key:
            raise RuntimeError(
                "SEARCH_RUNTIME_KEY_RECOVERY_FAIL"
            )

        for name in search_key_vars:
            env[name] = search_key

    if openai_key_vars:
        openai_key = az_tsv(
            [
                "cognitiveservices",
                "account",
                "keys",
                "list",
                "--name",
                OPENAI_ACCOUNT,
                "--resource-group",
                RG,
                "--query",
                "key1",
            ],
            timeout=60,
        )

        if not openai_key:
            raise RuntimeError(
                "OPENAI_RUNTIME_KEY_RECOVERY_FAIL"
            )

        for name in openai_key_vars:
            env[name] = openai_key

    print(
        "RUNTIME_ENV_RECOVERY=PASS",
        flush=True,
    )
    print(
        f"RUNTIME_ENV_DISCOVERED_SOURCE_VARS={len(names)}",
        flush=True,
    )
    print(
        f"SEARCH_RUNTIME_KEY_VARS_RECOVERED={len(search_key_vars)}",
        flush=True,
    )
    print(
        f"OPENAI_RUNTIME_KEY_VARS_RECOVERED={len(openai_key_vars)}",
        flush=True,
    )
    print(
        "RUNTIME_SECRET_VALUES_PRINTED=NO",
        flush=True,
    )
    print(
        "RUNTIME_SECRET_VALUES_PERSISTED=NO",
        flush=True,
    )

    return env


def proc_cmd(pid):
    try:
        raw = Path(
            f"/proc/{pid}/cmdline"
        ).read_bytes()
    except Exception:
        return ""

    return " ".join(
        part.decode(
            "utf-8",
            errors="ignore",
        )
        for part in raw.split(b"\0")
        if part
    )


def uvicorn_rows():
    rows = []

    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue

        pid = int(item.name)
        cmd = proc_cmd(pid)

        if (
            "uvicorn" not in cmd.lower()
            or "backend.app.main" not in cmd.lower()
        ):
            continue

        try:
            uid = os.stat(
                f"/proc/{pid}"
            ).st_uid
        except Exception:
            continue

        tokens = cmd.split()
        port = 8000

        for i, token in enumerate(tokens):
            if (
                token == "--port"
                and i + 1 < len(tokens)
            ):
                try:
                    port = int(tokens[i + 1])
                except Exception:
                    pass

        rows.append(
            {
                "pid": pid,
                "uid": uid,
                "port": port,
                "cmd": cmd,
            }
        )

    return rows


def start_uvicorn(
    port,
    host,
    env,
    log_path,
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
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )

    return proc, log


def get_json(url, timeout=10):
    with urlopen(
        Request(url, method="GET"),
        timeout=timeout,
    ) as response:
        return (
            response.status,
            json.loads(
                response.read().decode("utf-8")
            ),
            dict(response.headers.items()),
        )


def post_json(
    url,
    body,
    *,
    headers=None,
    timeout=180,
):
    merged = {
        "Content-Type": "application/json"
    }

    if headers:
        merged.update(headers)

    request = Request(
        url,
        data=json.dumps(
            body,
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers=merged,
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        return (
            response.status,
            json.loads(
                response.read().decode("utf-8")
            ),
            dict(response.headers.items()),
        )


def wait_runtime(
    port,
    expected_pid,
    proc,
    timeout=150,
):
    deadline = time.monotonic() + timeout
    last = None

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"FASTAPI_PROCESS_EXITED port={port} rc={proc.returncode}"
            )

        try:
            status, cosmos, _ = get_json(
                f"http://127.0.0.1:{port}/demo/cosmos-runtime",
                timeout=6,
            )
            last = cosmos

            if (
                status == 200
                and cosmos.get("version") == "p3a2-v1"
                and int(cosmos.get("pid")) == expected_pid
                and cosmos.get("data_plane") is True
            ):
                g_status, grounding, _ = get_json(
                    f"http://127.0.0.1:{port}/demo/grounding-runtime",
                    timeout=6,
                )

                if (
                    g_status == 200
                    and grounding.get("version") == "v6"
                    and grounding.get("ask_guard_wrapped") is True
                ):
                    return cosmos, grounding
        except Exception:
            pass

        time.sleep(2)

    raise RuntimeError(
        f"RUNTIME_WAIT_TIMEOUT port={port} last={last}"
    )


def stop_live_8000():
    rows = [
        row
        for row in uvicorn_rows()
        if row["port"] == 8000
        and row["uid"] == os.geteuid()
    ]

    if not rows:
        print(
            "LIVE_FASTAPI_EXISTING_PROCESS=NOT_FOUND_EXPECTED_AFTER_REBOOT",
            flush=True,
        )
        return []

    for row in rows:
        if row["pid"] == 1:
            raise RuntimeError(
                "LIVE_UVICORN_PID_1_SAFE_STOP"
            )

        try:
            os.kill(
                row["pid"],
                signal.SIGTERM,
            )
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + 20

    while time.monotonic() < deadline:
        remaining = [
            row
            for row in uvicorn_rows()
            if row["port"] == 8000
            and row["uid"] == os.geteuid()
        ]

        if not remaining:
            print(
                "LIVE_FASTAPI_STOP=PASS",
                flush=True,
            )
            return [
                row["pid"]
                for row in rows
            ]

        time.sleep(1)

    raise RuntimeError(
        "LIVE_FASTAPI_STOP_TIMEOUT"
    )


def sql_count():
    from mssql_python import connect

    conn = connect(
        (
            f"Server={SQL_SERVER};"
            f"Database={SQL_DATABASE};"
            "Authentication=ActiveDirectoryDefault;"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
        )
    )

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT_BIG(*) "
            "FROM techscope.FactAIRequest"
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def live_smoke():
    before = sql_count()

    print(
        f"AI_REQUESTS_BEFORE={before}",
        flush=True,
    )

    status, session, _ = post_json(
        "http://127.0.0.1:8000/cosmos/session",
        {
            "user_id": "p3a2-resume-v2",
            "channel": "automation",
        },
        timeout=30,
    )

    if status != 200:
        raise RuntimeError(
            "COSMOS_SESSION_CREATE_HTTP_FAIL"
        )

    session_id = str(
        session["session_id"]
    )

    print(
        "COSMOS_SESSION_CREATE=PASS",
        flush=True,
    )

    print(
        "LIVE_COSMOS_SMOKE_ASK=START",
        flush=True,
    )

    status, answer, headers = post_json(
        "http://127.0.0.1:8000/ask",
        {
            "question": (
                "What role does Azure Databricks play in TechScope? "
                "Include authoritative technology IDs and citations."
            )
        },
        headers={
            "X-TechScope-Session-Id": session_id,
            "X-TechScope-User-Id": "p3a2-resume-v2",
            "X-TechScope-Channel": "automation",
        },
        timeout=180,
    )

    print(
        "LIVE_COSMOS_SMOKE_ASK=PASS",
        flush=True,
    )

    if status != 200:
        raise RuntimeError(
            "LIVE_ASK_HTTP_FAIL"
        )

    citations = list(
        answer.get("citations") or []
    )
    tech_ids = list(
        answer.get(
            "grounded_technology_ids"
        )
        or []
    )

    if answer.get("grounded") is not True:
        raise RuntimeError(
            "LIVE_ASK_GROUNDED_TRUE=FAIL"
        )

    if not citations:
        raise RuntimeError(
            "LIVE_ASK_CITATIONS=0"
        )

    if not tech_ids:
        raise RuntimeError(
            "LIVE_ASK_TECH_IDS=0"
        )

    lower_headers = {
        str(k).lower(): v
        for k, v in headers.items()
    }

    persisted = str(
        lower_headers.get(
            "x-techscope-cosmos-persisted",
            "",
        )
    ).lower()

    interaction_id = str(
        lower_headers.get(
            "x-techscope-interaction-id",
            "",
        )
    )

    returned_session = str(
        lower_headers.get(
            "x-techscope-session-id",
            "",
        )
    )

    if persisted != "true":
        raise RuntimeError(
            "COSMOS_ASK_PERSISTENCE_HEADER=FAIL"
        )

    if returned_session != session_id:
        raise RuntimeError(
            "COSMOS_SESSION_HEADER_MISMATCH"
        )

    if not interaction_id:
        raise RuntimeError(
            "COSMOS_INTERACTION_ID_MISSING"
        )

    after = sql_count()

    if after - before != 1:
        raise RuntimeError(
            f"SQL_AI_REQUEST_DELTA_FAIL before={before} after={after}"
        )

    print(
        f"AI_REQUESTS={before}->{after}",
        flush=True,
    )
    print(
        "SQL_AI_REQUEST_DELTA=PASS +1",
        flush=True,
    )
    print(
        "COSMOS_ASK_PERSISTENCE_HEADER=PASS",
        flush=True,
    )

    status, bundle, _ = get_json(
        f"http://127.0.0.1:8000/cosmos/session/{session_id}",
        timeout=30,
    )

    if status != 200:
        raise RuntimeError(
            "COSMOS_SESSION_READ_HTTP_FAIL"
        )

    messages = [
        item
        for item in (
            bundle.get("messages") or []
        )
        if str(
            item.get(
                "interaction_id",
                "",
            )
        )
        == interaction_id
    ]

    roles = [
        item.get("role")
        for item in messages
    ]

    if roles != [
        "user",
        "assistant",
    ]:
        raise RuntimeError(
            f"COSMOS_CONVERSATION_ROLES_FAIL={roles}"
        )

    print(
        "SESSION_PERSISTENCE=PASS",
        flush=True,
    )
    print(
        "CONVERSATION_PERSISTENCE=PASS MESSAGES=2",
        flush=True,
    )

    status, _, _ = post_json(
        "http://127.0.0.1:8000/cosmos/feedback",
        {
            "session_id": session_id,
            "interaction_id": interaction_id,
            "score": 1,
            "comment": "P3A2 resume v2 verification",
            "user_id": "p3a2-resume-v2",
        },
        timeout=30,
    )

    if status != 200:
        raise RuntimeError(
            "COSMOS_FEEDBACK_CREATE_HTTP_FAIL"
        )

    status, bundle2, _ = get_json(
        f"http://127.0.0.1:8000/cosmos/session/{session_id}",
        timeout=30,
    )

    feedback = [
        item
        for item in (
            bundle2.get("feedback") or []
        )
        if str(
            item.get(
                "interaction_id",
                "",
            )
        )
        == interaction_id
    ]

    if len(feedback) != 1:
        raise RuntimeError(
            f"COSMOS_FEEDBACK_READBACK_FAIL count={len(feedback)}"
        )

    print(
        "FEEDBACK_PERSISTENCE=PASS FEEDBACK=1",
        flush=True,
    )

    try:
        status, _, _ = post_json(
            "http://127.0.0.1:8000/demo/powerbi-sync",
            {},
            timeout=90,
        )

        if status == 200:
            print(
                "POWERBI_SNAPSHOT_SYNC=PASS",
                flush=True,
            )
        else:
            print(
                "POWERBI_SNAPSHOT_SYNC=NONBLOCKING_FAIL",
                flush=True,
            )
    except Exception as exc:
        print(
            "POWERBI_SNAPSHOT_SYNC=NONBLOCKING_FAIL "
            + type(exc).__name__,
            flush=True,
        )

    return {
        "session_id": session_id,
        "interaction_id": interaction_id,
        "messages": len(messages),
        "feedback": len(feedback),
        "ai_requests_before": before,
        "ai_requests_after": after,
        "grounded": True,
        "citation_count": len(citations),
        "technology_id_count": len(tech_ids),
    }


def update_block(
    path,
    start,
    end,
    body,
):
    if not path.exists():
        return

    text = path.read_text(
        encoding="utf-8"
    )

    block = (
        start
        + "\n"
        + body.strip()
        + "\n"
        + end
    )

    pattern = re.compile(
        re.escape(start)
        + r".*?"
        + re.escape(end),
        re.DOTALL,
    )

    if pattern.search(text):
        text = pattern.sub(
            block,
            text,
            count=1,
        )
    else:
        text += "\n\n" + block + "\n"

    path.write_text(
        text,
        encoding="utf-8",
    )


def update_docs(smoke):
    if STATUS_DOC.exists():
        text = STATUS_DOC.read_text(
            encoding="utf-8"
        )

        lines = []

        for line in text.splitlines():
            if (
                "CMP_COSMOS" in line
                and "Blocked" in line
            ):
                line = line.replace(
                    "Blocked",
                    "Implemented",
                )

            lines.append(line)

        STATUS_DOC.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    update_block(
        STATUS_DOC,
        "<!-- TECHSCOPE_COSMOS_RUNTIME:START -->",
        "<!-- TECHSCOPE_COSMOS_RUNTIME:END -->",
        f"""
## Cosmos Runtime Persistence

- `CMP_COSMOS = Implemented`
- Authentication: `Microsoft Entra RBAC / DefaultAzureCredential`
- Session persistence: `PASS`
- Conversation persistence: `PASS`
- Feedback persistence: `PASS`
- Account key persisted: `NO`
- Verified session: `{smoke['session_id']}`
- Verified messages: `{smoke['messages']}`
- Verified feedback rows: `{smoke['feedback']}`
- AI Requests: `{smoke['ai_requests_before']} -> {smoke['ai_requests_after']}`
""",
    )

    update_block(
        EVIDENCE_DOC,
        "<!-- TECHSCOPE_COSMOS_RUNTIME_EVIDENCE:START -->",
        "<!-- TECHSCOPE_COSMOS_RUNTIME_EVIDENCE:END -->",
        f"""
## Cosmos Runtime Evidence

- Source: `backend/app/cosmos_interaction_store.py`
- Runtime: `backend/app/cosmos_runtime.py`
- Config: `config/cosmos-runtime.json`
- Result: `results/latest/p3a2-cosmos-runtime.json`
- SOURCE: `evidence/cosmos/p3a2-cosmos-source.json`
- EXECUTION: `evidence/cosmos/p3a2-cosmos-execution.json`
- OUTPUT: `evidence/cosmos/p3a2-cosmos-output.json`
- Verified session: `{smoke['session_id']}`
- Conversation messages: `{smoke['messages']}`
- Feedback rows: `{smoke['feedback']}`
""",
    )

    print(
        "DOC_STATUS_COSMOS=PASS",
        flush=True,
    )
    print(
        "DOC_EVIDENCE_COSMOS=PASS",
        flush=True,
    )


def write_evidence(
    runtime,
    grounding,
    live_pid,
    stopped,
    smoke,
):
    EVIDENCE.mkdir(
        parents=True,
        exist_ok=True,
    )
    RESULT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source = {
        "status": "PASS",
        "type": "SOURCE",
        "component": "CMP_COSMOS",
        "files": [
            "backend/app/cosmos_interaction_store.py",
            "backend/app/cosmos_runtime.py",
            "backend/app/main.py",
            "backend/requirements-cosmos.txt",
            "config/cosmos-runtime.json",
        ],
    }

    execution = {
        "status": "PASS",
        "type": "EXECUTION",
        "component": "CMP_COSMOS",
        "runtime": runtime,
        "grounding_runtime": grounding,
        "live_pid": live_pid,
        "stopped_pids": stopped,
        "runtime_env_recovery": "Azure CLI / memory only",
        "secret_values_printed": False,
        "secret_values_persisted": False,
        "auth": "DefaultAzureCredential / Microsoft Entra RBAC",
    }

    output = {
        "status": "PASS",
        "type": "OUTPUT",
        "component": "CMP_COSMOS",
        "session_persistence": True,
        "conversation_persistence": True,
        "feedback_persistence": True,
        "smoke": smoke,
    }

    (EVIDENCE / "p3a2-cosmos-source.json").write_text(
        json.dumps(
            source,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (EVIDENCE / "p3a2-cosmos-execution.json").write_text(
        json.dumps(
            execution,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (EVIDENCE / "p3a2-cosmos-output.json").write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    RESULT.write_text(
        json.dumps(
            {
                "status": "PASS",
                "stage": "P3A2",
                "component": "CMP_COSMOS",
                "component_status": "Implemented",
                "runtime_version": "p3a2-v1",
                "session_persistence": "PASS",
                "conversation_persistence": "PASS",
                "feedback_persistence": "PASS",
                "grounding_v6_preserved": True,
                "secret_values_persisted": False,
                "live_pid": live_pid,
                "smoke": smoke,
                "next": "P3B_TEAMS_LIVE_TENANT_E2E",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "COSMOS_SOURCE_EVIDENCE=PASS",
        flush=True,
    )
    print(
        "COSMOS_EXECUTION_EVIDENCE=PASS",
        flush=True,
    )
    print(
        "COSMOS_OUTPUT_EVIDENCE=PASS",
        flush=True,
    )


def main():
    print(
        "P3A2_COSMOS_RUNTIME_RESUME_V2=START",
        flush=True,
    )
    print(
        "AZURE_RESOURCE_CREATION=NO",
        flush=True,
    )
    print(
        "AZURE_RESOURCE_DELETION=NO",
        flush=True,
    )
    print(
        "REAL_AI_ASK_CALLS=1",
        flush=True,
    )

    verify_installed_source()
    compile_and_lint("RESUME_PRECHECK")
    env = build_runtime_env()

    preflight_proc, preflight_log = start_uvicorn(
        8015,
        "127.0.0.1",
        env,
        "/tmp/techscope-p3a2-resume-preflight.log",
    )

    try:
        runtime_pre, grounding_pre = wait_runtime(
            8015,
            preflight_proc.pid,
            preflight_proc,
            timeout=150,
        )

        print(
            "COSMOS_RUNTIME_PREFLIGHT=PASS PORT=8015",
            flush=True,
        )
        print(
            "GROUNDING_V6_PREFLIGHT=PASS",
            flush=True,
        )
    except Exception:
        try:
            preflight_log.flush()
            text = Path(
                "/tmp/techscope-p3a2-resume-preflight.log"
            ).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            print(
                "----- P3A2 RESUME PREFLIGHT LOG TAIL -----",
                flush=True,
            )
            print(
                text[-7000:],
                flush=True,
            )
        except Exception:
            pass
        raise
    finally:
        if preflight_proc.poll() is None:
            preflight_proc.terminate()
            try:
                preflight_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                preflight_proc.kill()
                preflight_proc.wait(timeout=5)
        preflight_log.close()

    stopped = stop_live_8000()

    live_proc, live_log = start_uvicorn(
        8000,
        "0.0.0.0",
        env,
        "/tmp/techscope-p3a2-resume-live.log",
    )

    try:
        runtime_live, grounding_live = wait_runtime(
            8000,
            live_proc.pid,
            live_proc,
            timeout=150,
        )
    except Exception:
        try:
            live_log.flush()
            text = Path(
                "/tmp/techscope-p3a2-resume-live.log"
            ).read_text(
                encoding="utf-8",
                errors="ignore",
            )
            print(
                "----- P3A2 RESUME LIVE LOG TAIL -----",
                flush=True,
            )
            print(
                text[-7000:],
                flush=True,
            )
        except Exception:
            pass
        raise

    print(
        f"LIVE_FASTAPI_NEW_PID={live_proc.pid}",
        flush=True,
    )
    print(
        "LIVE_COSMOS_RUNTIME_VERSION=p3a2-v1",
        flush=True,
    )
    print(
        "LIVE_COSMOS_DATA_PLANE=PASS",
        flush=True,
    )
    print(
        "GROUNDING_V6_REGRESSION=PASS",
        flush=True,
    )

    smoke = live_smoke()
    update_docs(smoke)

    shutil.copy2(
        __file__,
        ROOT / "tools/p3a2_cosmos_runtime_resume_v2.py",
    )

    write_evidence(
        runtime_live,
        grounding_live,
        live_proc.pid,
        stopped,
        smoke,
    )

    compile_and_lint("FINAL")

    print(
        "CMP_COSMOS_STATUS=IMPLEMENTED",
        flush=True,
    )
    print(
        "SESSION_PERSISTENCE=PASS",
        flush=True,
    )
    print(
        "CONVERSATION_PERSISTENCE=PASS",
        flush=True,
    )
    print(
        "FEEDBACK_PERSISTENCE=PASS",
        flush=True,
    )
    print(
        "REPORT=results/latest/p3a2-cosmos-runtime.json",
        flush=True,
    )
    print(
        "P3A2_COSMOS_RUNTIME_RESUME_V2=PASS",
        flush=True,
    )
    print(
        "NEXT_ACTION=P3B_TEAMS_LIVE_TENANT_E2E",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
