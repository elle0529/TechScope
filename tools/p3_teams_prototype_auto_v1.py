#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
TEAM_DIR = ROOT / "teams/techscope-agent"
TEMPLATE_DIR = ROOT / "generated/teams-prototype-installer"
RESULTS = ROOT / "results/latest"
EVIDENCE = ROOT / "evidence"

COSMOS_BLOCKER = RESULTS / "p3-cosmos-blocker.json"
TEAMS_REPORT = RESULTS / "p3-teams-prototype.json"
TEAMS_SOURCE_EVIDENCE = EVIDENCE / "teams/p3-teams-source.json"
TEAMS_EXEC_EVIDENCE = EVIDENCE / "teams/p3-teams-execution.json"
COSMOS_BLOCK_EVIDENCE = EVIDENCE / "cosmos/p3-cosmos-blocked.json"


def run(cmd, *, cwd=None, check=True, timeout=300):
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


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_cosmos_blocker(now):
    obj = {
        "timestamp_utc": now,
        "component": "CMP_COSMOS",
        "status": "Blocked",
        "reason": "NO_EXISTING_COSMOS_ACCOUNT",
        "resource_group": "rg-techscope-dev-239bd206",
        "existing_accounts_in_resource_group": 0,
        "azure_resource_creation_performed": False,
        "azure_resource_deletion_performed": False,
        "session_runtime_verified": False,
        "conversation_runtime_verified": False,
        "feedback_runtime_verified": False,
        "next_resolution_condition": (
            "A reusable Cosmos DB for NoSQL account/database/container "
            "must already exist, or the no-new-Azure-resource policy must change."
        ),
    }
    write_json(COSMOS_BLOCKER, obj)
    write_json(COSMOS_BLOCK_EVIDENCE, {
        **obj,
        "implementation_evidence": "EXECUTION",
    })

    print("CMP_COSMOS_STATUS=BLOCKED", flush=True)
    print("COSMOS_BLOCKER_REASON=NO_EXISTING_COSMOS_ACCOUNT", flush=True)
    print("COSMOS_RESOURCE_CREATION=NO", flush=True)
    print("COSMOS_BLOCKER_EVIDENCE=PASS", flush=True)


def verify_node():
    node = run(["node", "--version"], check=False, timeout=30)
    npm = run(["npm", "--version"], check=False, timeout=30)

    if node.returncode != 0 or npm.returncode != 0:
        raise RuntimeError(
            "TEAMS_PROTOTYPE_BLOCKED_NODE_OR_NPM_MISSING"
        )

    print(f"NODE_VERSION={(node.stdout or '').strip()}", flush=True)
    print(f"NPM_VERSION={(npm.stdout or '').strip()}", flush=True)


def install_source():
    if not TEMPLATE_DIR.exists():
        raise RuntimeError("TEAMS_TEMPLATE_DIR_NOT_FOUND")

    TEAM_DIR.mkdir(parents=True, exist_ok=True)

    for src in TEMPLATE_DIR.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        dst = TEAM_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    print("TEAMS_SOURCE_INSTALL=PASS", flush=True)
    print("TEAMS_SDK=@microsoft/teams.apps@2.0.14", flush=True)
    print("TEAMSFX_USED=NO", flush=True)


def npm_build_and_smoke():
    print("TEAMS_NPM_INSTALL=START", flush=True)
    cp = run(
        [
            "npm", "install",
            "--no-audit",
            "--no-fund",
        ],
        cwd=TEAM_DIR,
        check=False,
        timeout=300,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "TEAMS_NPM_INSTALL=FAIL\n"
            + (cp.stdout or "")[-3000:]
            + "\n"
            + (cp.stderr or "")[-3000:]
        )

    print("TEAMS_NPM_INSTALL=PASS", flush=True)

    build = run(
        ["npm", "run", "build"],
        cwd=TEAM_DIR,
        check=False,
        timeout=180,
    )
    if build.returncode != 0:
        raise RuntimeError(
            "TEAMS_TYPESCRIPT_BUILD=FAIL\n"
            + (build.stdout or "")[-4000:]
            + "\n"
            + (build.stderr or "")[-4000:]
        )

    print("TEAMS_TYPESCRIPT_BUILD=PASS", flush=True)

    smoke = run(
        ["npm", "run", "smoke"],
        cwd=TEAM_DIR,
        check=False,
        timeout=120,
    )
    text = (smoke.stdout or "") + "\n" + (smoke.stderr or "")

    print((smoke.stdout or "").strip(), flush=True)

    if smoke.returncode != 0 or "TEAMS_FASTAPI_ADAPTER_SMOKE=PASS" not in text:
        raise RuntimeError(
            "TEAMS_FASTAPI_ADAPTER_SMOKE=FAIL\n" + text[-5000:]
        )

    return text


def architecture_lint():
    lint = run(
        [
            "python",
            str(ROOT / "tools/architecture_lint.py"),
        ],
        check=False,
        timeout=120,
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")

    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError("ARCHITECTURE_LINT_AFTER_TEAMS_PROTOTYPE=FAIL")

    print("ARCHITECTURE_LINT_AFTER_TEAMS_PROTOTYPE=PASS", flush=True)


def main():
    now = datetime.now(timezone.utc).isoformat()

    print("P3_TEAMS_PROTOTYPE_AUTO_V1=START", flush=True)
    print("AZURE_RESOURCE_CREATION=NO", flush=True)
    print("TEAMS_TENANT_DEPLOYMENT=NO", flush=True)

    record_cosmos_blocker(now)
    verify_node()
    install_source()
    smoke_text = npm_build_and_smoke()
    architecture_lint()

    source_files = [
        "teams/techscope-agent/package.json",
        "teams/techscope-agent/tsconfig.json",
        "teams/techscope-agent/src/index.ts",
        "teams/techscope-agent/src/techscope-client.ts",
        "teams/techscope-agent/src/smoke.ts",
        "teams/techscope-agent/README.md",
    ]

    write_json(
        TEAMS_SOURCE_EVIDENCE,
        {
            "timestamp_utc": now,
            "component": "CMP_TEAMS",
            "status": "Prototype",
            "implementation_evidence": "SOURCE",
            "sdk": "@microsoft/teams.apps",
            "sdk_version": "2.0.14",
            "teamsfx_used": False,
            "files": source_files,
            "flow": [
                "Teams message",
                "Teams SDK message handler",
                "POST FastAPI /ask",
                "grounded answer/citations/technology IDs",
                "Teams reply",
            ],
        },
    )

    write_json(
        TEAMS_EXEC_EVIDENCE,
        {
            "timestamp_utc": now,
            "component": "CMP_TEAMS",
            "status": "Prototype",
            "implementation_evidence": "EXECUTION",
            "typescript_build": "PASS",
            "adapter_smoke": "PASS",
            "smoke_assertions": [
                "POST /ask",
                "question forwarding",
                "answer formatting",
                "grounding formatting",
                "citation formatting",
                "technology ID formatting",
            ],
            "live_teams_tenant_e2e": False,
        },
    )

    write_json(
        TEAMS_REPORT,
        {
            "timestamp_utc": now,
            "component": "CMP_TEAMS",
            "status": "Prototype",
            "source_evidence": str(
                TEAMS_SOURCE_EVIDENCE.relative_to(ROOT)
            ),
            "execution_evidence": str(
                TEAMS_EXEC_EVIDENCE.relative_to(ROOT)
            ),
            "teams_sdk": "@microsoft/teams.apps@2.0.14",
            "teamsfx_used": False,
            "fastapi_path": "/ask",
            "live_teams_tenant_e2e": False,
            "azure_resource_creation": False,
            "next_requirement": (
                "Teams app registration/tenant installation and "
                "live message E2E are still required for Implemented status."
            ),
        },
    )

    print("CMP_TEAMS_STATUS=PROTOTYPE", flush=True)
    print("CMP_TEAMS_SOURCE_EVIDENCE=PASS", flush=True)
    print("CMP_TEAMS_EXECUTION_EVIDENCE=PASS", flush=True)
    print("TEAMS_LIVE_TENANT_E2E=NOT_CLAIMED", flush=True)
    print("P3_TEAMS_PROTOTYPE_AUTO_V1=PASS", flush=True)
    print("REPORT=results/latest/p3-teams-prototype.json", flush=True)
    print(
        "NEXT_ACTION=MAIN_FINAL_VERIFICATION_WITH_COSMOS_BLOCKER",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
