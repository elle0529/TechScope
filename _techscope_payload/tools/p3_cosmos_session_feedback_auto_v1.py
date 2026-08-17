#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
RG = "rg-techscope-dev-239bd206"
SUBSCRIPTION = "20c99d23-dcad-42e2-bca2-b511133f4140"

PREFLIGHT = ROOT / "results/latest/p3-preflight-v3.json"
CONFIG = ROOT / "config/p3-cosmos.json"
STORE = ROOT / "backend/app/cosmos_interaction_store.py"
ROUTER = ROOT / "backend/app/p3_router.py"
MAIN = ROOT / "backend/app/main.py"
REPORT = ROOT / "results/latest/p3-cosmos-session-feedback.json"
TEMPLATES = ROOT / "generated/p3-installer-templates"

SAFE_CONTAINER_TERMS = (
    "techscope", "session", "conversation", "interaction", "feedback"
)


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd, cwd=ROOT, text=True, capture_output=True,
        check=False, timeout=timeout
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


def az_json(args, timeout=120):
    cp = run(
        ["az", *args, "--only-show-errors", "-o", "json"],
        check=False, timeout=timeout
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "AZ_COMMAND_FAILED\n"
            + "az " + " ".join(args)
            + "\n" + (cp.stderr or "")[-4000:]
        )
    return json.loads(cp.stdout or "null")


def ensure_context():
    obj = az_json(["account", "show"], timeout=60)
    if obj.get("id") != SUBSCRIPTION:
        run(["az", "account", "set", "--subscription", SUBSCRIPTION], timeout=60)
        obj = az_json(["account", "show"], timeout=60)

    print(f"AZURE_SUBSCRIPTION=PASS {obj.get('id')}", flush=True)
    print(f"AZURE_USER={((obj.get('user') or {}).get('name'))}", flush=True)


def load_preflight():
    if not PREFLIGHT.exists():
        raise RuntimeError("P3_PREFLIGHT_REPORT_NOT_FOUND=" + str(PREFLIGHT))

    obj = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    print("P3_PREFLIGHT_REPORT=PASS", flush=True)
    print(f"P3_PREFLIGHT_ROUTES={len(obj.get('routes') or [])}", flush=True)
    print(
        "P3_PREFLIGHT_AZURE_COSMOS_DEP="
        + ("YES" if (obj.get("dependencies") or {}).get("azure-cosmos") else "NO"),
        flush=True,
    )
    return obj


def choose_account():
    accounts = az_json(["cosmosdb", "list", "--resource-group", RG]) or []
    print(f"COSMOS_ACCOUNTS_IN_RG={len(accounts)}", flush=True)

    candidates = [
        a for a in accounts
        if str(a.get("kind") or "").lower() == "globaldocumentdb"
    ]

    if not candidates:
        all_accounts = az_json(["cosmosdb", "list"]) or []
        candidates = [
            a for a in all_accounts
            if str(a.get("kind") or "").lower() == "globaldocumentdb"
            and "techscope" in str(a.get("name") or "").lower()
        ]

    if not candidates:
        print("COSMOS_REUSE_CANDIDATE=NOT_FOUND", flush=True)
        print("AZURE_RESOURCE_CREATION=SKIPPED_BY_POLICY", flush=True)
        print("P3_RUNTIME_STATUS=BLOCKED_NO_EXISTING_COSMOS_ACCOUNT", flush=True)
        return None

    if len(candidates) > 1:
        exact = [
            a for a in candidates
            if "techscope" in str(a.get("name") or "").lower()
        ]
        if len(exact) == 1:
            candidates = exact
        else:
            raise RuntimeError(
                "COSMOS_REUSE_CANDIDATE=AMBIGUOUS "
                + ",".join(str(a.get("name")) for a in candidates)
            )

    a = candidates[0]
    name = str(a["name"])
    rg = str(a.get("resourceGroup") or RG)
    endpoint = str(a.get("documentEndpoint") or "")

    if not endpoint:
        details = az_json([
            "cosmosdb", "show",
            "--name", name,
            "--resource-group", rg,
        ])
        endpoint = str(details.get("documentEndpoint") or "")

    if not endpoint:
        raise RuntimeError("COSMOS_ENDPOINT_NOT_FOUND")

    print(f"COSMOS_ACCOUNT=REUSE {name}", flush=True)
    print(f"COSMOS_RESOURCE_GROUP={rg}", flush=True)
    print("COSMOS_ENDPOINT=DISCOVERED", flush=True)

    return {
        "account_name": name,
        "resource_group": rg,
        "endpoint": endpoint,
    }


def choose_database(account):
    dbs = az_json([
        "cosmosdb", "sql", "database", "list",
        "--account-name", account["account_name"],
        "--resource-group", account["resource_group"],
    ]) or []

    print(f"COSMOS_SQL_DATABASES={len(dbs)}", flush=True)

    if not dbs:
        print("COSMOS_DATABASE=NOT_FOUND", flush=True)
        print("AZURE_RESOURCE_CREATION=SKIPPED_BY_POLICY", flush=True)
        print("P3_RUNTIME_STATUS=BLOCKED_NO_EXISTING_COSMOS_DATABASE", flush=True)
        return None

    names = []
    for d in dbs:
        name = str(((d.get("resource") or {}).get("id")) or d.get("name") or "")
        if name:
            names.append(name)

    preferred = [
        n for n in names
        if "techscope" in n.lower()
        or "app" in n.lower()
        or "oper" in n.lower()
    ]

    if len(preferred) == 1:
        name = preferred[0]
    elif len(names) == 1:
        name = names[0]
    else:
        print("COSMOS_DATABASE_CANDIDATES=" + ",".join(names), flush=True)
        print("P3_RUNTIME_STATUS=BLOCKED_AMBIGUOUS_EXISTING_DATABASE", flush=True)
        return None

    print(f"COSMOS_DATABASE=REUSE {name}", flush=True)
    return name


def choose_container(account, database):
    containers = az_json([
        "cosmosdb", "sql", "container", "list",
        "--account-name", account["account_name"],
        "--resource-group", account["resource_group"],
        "--database-name", database,
    ]) or []

    print(f"COSMOS_CONTAINERS={len(containers)}", flush=True)

    if not containers:
        print("COSMOS_CONTAINER=NOT_FOUND", flush=True)
        print("AZURE_RESOURCE_CREATION=SKIPPED_BY_POLICY", flush=True)
        print("P3_RUNTIME_STATUS=BLOCKED_NO_EXISTING_COSMOS_CONTAINER", flush=True)
        return None

    parsed = []
    for c in containers:
        resource = c.get("resource") or {}
        name = str(resource.get("id") or c.get("name") or "")
        paths = ((resource.get("partitionKey") or {}).get("paths")) or []
        if name:
            parsed.append((name, paths))

    preferred = [
        x for x in parsed
        if any(term in x[0].lower() for term in SAFE_CONTAINER_TERMS)
    ]

    if len(preferred) == 1:
        chosen = preferred[0]
    elif len(parsed) == 1 and any(
        term in parsed[0][0].lower() for term in SAFE_CONTAINER_TERMS
    ):
        chosen = parsed[0]
    else:
        print(
            "COSMOS_CONTAINER_CANDIDATES="
            + ",".join(x[0] for x in parsed),
            flush=True,
        )
        print(
            "P3_RUNTIME_STATUS=BLOCKED_NO_UNAMBIGUOUS_DEDICATED_CONTAINER",
            flush=True,
        )
        return None

    name, paths = chosen
    if not paths:
        raise RuntimeError("COSMOS_CONTAINER_PARTITION_KEY_NOT_FOUND")

    partition_path = str(paths[0])
    print(f"COSMOS_CONTAINER=REUSE {name}", flush=True)
    print(f"COSMOS_PARTITION_PATH={partition_path}", flush=True)

    return {"name": name, "partition_path": partition_path}


def ensure_dependencies():
    cp = run(
        [sys.executable, "-c", "import azure.cosmos, azure.identity; print('OK')"],
        check=False, timeout=30
    )
    if cp.returncode == 0:
        print("P3_DEPENDENCIES=ALREADY_PRESENT", flush=True)
        return

    print("P3_DEPENDENCIES=INSTALL_START", flush=True)
    run(
        [
            sys.executable, "-m", "pip", "install",
            "azure-cosmos>=4.9,<5",
            "azure-identity>=1.17,<2",
        ],
        timeout=180,
    )
    print("P3_DEPENDENCIES=INSTALL_PASS", flush=True)


def write_source(account, database, container):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        json.dumps(
            {
                "endpoint": account["endpoint"],
                "account_name": account["account_name"],
                "resource_group": account["resource_group"],
                "database": database,
                "container": container["name"],
                "partition_path": container["partition_path"],
                "credential_mode": "default_azure_credential_then_runtime_key",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if not TEMPLATES.exists():
        raise RuntimeError("P3_INSTALLER_TEMPLATES_NOT_FOUND")

    shutil.copy2(TEMPLATES / "cosmos_interaction_store.py", STORE)
    shutil.copy2(TEMPLATES / "p3_router.py", ROUTER)

    print("P3_SOURCE_COSMOS_STORE=PASS", flush=True)
    print("P3_SOURCE_ROUTER=PASS", flush=True)
    print("P3_SOURCE_CONFIG=PASS NON_SECRET", flush=True)


def patch_main():
    text = MAIN.read_text(encoding="utf-8")
    import_marker = "from .p3_router import router as p3_router"
    include_marker = "app.include_router(p3_router)"

    if import_marker not in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, import_marker)
        text = "\n".join(lines) + "\n"

    if include_marker not in text:
        tree = ast.parse(text)
        app_line = None

        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets):
                    if isinstance(node.value, ast.Call):
                        fn = node.value.func
                        if (
                            isinstance(fn, ast.Name) and fn.id == "FastAPI"
                        ) or (
                            isinstance(fn, ast.Attribute) and fn.attr == "FastAPI"
                        ):
                            app_line = node.end_lineno
                            break

        if app_line is None:
            raise RuntimeError("FASTAPI_APP_ASSIGNMENT_NOT_FOUND")

        lines = text.splitlines()
        lines.insert(app_line, include_marker)
        text = "\n".join(lines) + "\n"

    MAIN.write_text(text, encoding="utf-8")
    print("P3_MAIN_ROUTER_WIRING=PASS", flush=True)


def compile_and_lint():
    for p in [STORE, ROUTER, MAIN]:
        cp = run(
            [sys.executable, "-m", "py_compile", str(p)],
            check=False, timeout=30
        )
        if cp.returncode != 0:
            raise RuntimeError(f"PY_COMPILE_FAIL={p}\n{cp.stderr}")

    print("P3_PY_COMPILE=PASS", flush=True)

    lint = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False, timeout=90
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")
    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-4000:], flush=True)
        raise RuntimeError("P3_ARCHITECTURE_LINT=FAIL")

    print("P3_ARCHITECTURE_LINT=PASS", flush=True)


def verify_runtime():
    sys.path.insert(0, str(ROOT))
    from backend.app.cosmos_interaction_store import CosmosInteractionStore

    store = CosmosInteractionStore()
    print(f"COSMOS_AUTH_MODE={store.credential_mode}", flush=True)

    s = store.create_session(title="P3 implementation verification")
    sid = s["sessionId"]
    request_id = "p3-verify-" + sid[:8]

    i = store.add_interaction(
        session_id=sid,
        request_id=request_id,
        question="TechScope P3 persistence verification",
        answer="Session, interaction, and feedback persistence verified.",
        grounded=True,
        citations=[],
        technology_ids=[],
    )
    f = store.add_feedback(
        session_id=sid,
        request_id=request_id,
        rating=1,
        comment="P3 verification record",
    )

    docs = store.get_session_documents(sid)
    types = sorted(str(d.get("type")) for d in docs)

    if len(docs) < 3:
        raise RuntimeError(f"COSMOS_RUNTIME_VERIFY_COUNT={len(docs)} expected>=3")

    for required in ["session", "interaction", "feedback"]:
        if required not in types:
            raise RuntimeError(f"COSMOS_RUNTIME_VERIFY_MISSING_TYPE={required}")

    print(f"COSMOS_SESSION_CREATE=PASS SESSION_ID={sid}", flush=True)
    print(f"COSMOS_INTERACTION_PERSIST=PASS ID={i['id']}", flush=True)
    print(f"COSMOS_FEEDBACK_PERSIST=PASS ID={f['id']}", flush=True)
    print(f"COSMOS_SESSION_QUERY=PASS DOCUMENTS={len(docs)}", flush=True)

    return {
        "credential_mode": store.credential_mode,
        "session_id": sid,
        "request_id": request_id,
        "document_count": len(docs),
        "document_types": types,
    }


def main():
    print("P3_COSMOS_SESSION_FEEDBACK_AUTO_V1=START", flush=True)
    print("AZURE_RESOURCE_CREATION=NO", flush=True)
    print("AZURE_RESOURCE_DELETION=NO", flush=True)

    ensure_context()
    load_preflight()

    account = choose_account()
    if account is None:
        return 20

    database = choose_database(account)
    if database is None:
        return 21

    container = choose_container(account, database)
    if container is None:
        return 22

    ensure_dependencies()
    write_source(account, database, container)
    patch_main()
    compile_and_lint()
    runtime = verify_runtime()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "status": "PASS",
                "component": "CMP_COSMOS",
                "account": account["account_name"],
                "resource_group": account["resource_group"],
                "database": database,
                "container": container["name"],
                "partition_path": container["partition_path"],
                "runtime": runtime,
                "resource_creation": False,
                "resource_deletion": False,
                "secret_persisted": False,
                "routes": [
                    "POST /p3/sessions",
                    "POST /p3/interactions",
                    "POST /p3/feedback",
                    "GET /p3/sessions/{session_id}",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("CMP_COSMOS=PASS", flush=True)
    print("P3_SESSION_PERSISTENCE=PASS", flush=True)
    print("P3_CONVERSATION_PERSISTENCE=PASS", flush=True)
    print("P3_FEEDBACK_PERSISTENCE=PASS", flush=True)
    print("P3_SECRET_PERSISTED=NO", flush=True)
    print("REPORT=results/latest/p3-cosmos-session-feedback.json", flush=True)
    print("NEXT_ACTION=CHECKPOINT_AND_TEAMS", flush=True)
    print("P3_COSMOS_SESSION_FEEDBACK_AUTO_V1=PASS", flush=True)
    return 0


if __name__ == "__main__":
    rc = main()
    if rc in {20, 21, 22}:
        print("P3_COSMOS_SESSION_FEEDBACK_AUTO_V1=BLOCKED_SAFE_STOP", flush=True)
    raise SystemExit(rc)
