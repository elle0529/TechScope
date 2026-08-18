#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "results" / "latest"
RUNTIME_EVIDENCE_DIR = ROOT / "evidence" / "runtime"

MARKER = "TECHSCOPE_RUNTIME_CLI_V1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

REQUIRED_PRIOR_ARTIFACTS = [
    ROOT / "results/latest/p1d-summary.json",
    ROOT / "results/latest/p2b-summary.json",
    ROOT / "evidence/rag/p2b-cloud-e2e.json",
    ROOT / "results/latest/p3a2-cosmos-runtime.json",
    ROOT / "results/latest/p3b-teams-live-e2e.json",
]

FORBIDDEN_TRACKED_PATTERNS = (
    "/.azure/",
    "/node_modules/",
    "/.git/",
)
FORBIDDEN_TRACKED_BASENAMES = {
    ".env",
    ".databrickscfg",
}


def emit(key: str, value: object = "PASS") -> None:
    print(f"{key}={value}", flush=True)


def http_json(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> tuple[int, dict, dict[str, str]]:
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    req = Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, payload, response_headers
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP_{exc.code} {method} {url}\n{raw[:2000]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"HTTP_CONNECTION_FAIL {method} {url}: {exc}") from exc


def run(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def read_status(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return "UNPARSEABLE"
    return str(obj.get("status") or obj.get("live_tenant_e2e") or "")


def verify_prior_evidence() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in REQUIRED_PRIOR_ARTIFACTS:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if not path.exists():
            raise RuntimeError(f"REQUIRED_PRIOR_ARTIFACT_MISSING={rel}")
        result[rel] = read_status(path) or "PRESENT"
        emit("PRIOR_ARTIFACT", f"PASS {rel}")
    return result


def verify_tracked_secret_paths() -> list[str]:
    cp = run(["git", "ls-files", "-z"], timeout=30)
    if cp.returncode != 0:
        raise RuntimeError("GIT_LS_FILES_FAIL\n" + cp.stderr[-2000:])

    tracked = [p for p in cp.stdout.split("\0") if p]
    bad: list[str] = []
    for path in tracked:
        normalized = "/" + path.replace("\\", "/") + "/"
        base = Path(path).name.lower()
        if base in FORBIDDEN_TRACKED_BASENAMES:
            bad.append(path)
            continue
        if any(pattern in normalized.lower() for pattern in FORBIDDEN_TRACKED_PATTERNS):
            bad.append(path)

    if bad:
        raise RuntimeError(
            "GIT_TRACKED_SECRET_PATH_SCAN=FAIL\n" + "\n".join(sorted(bad))
        )

    emit("GIT_TRACKED_SECRET_PATH_SCAN", "PASS")
    return tracked


def architecture_lint() -> dict:
    cp = run([sys.executable, "tools/architecture_lint.py"], timeout=120)
    if cp.stdout:
        print(cp.stdout, end="" if cp.stdout.endswith("\n") else "\n", flush=True)
    if cp.stderr:
        print(cp.stderr, end="" if cp.stderr.endswith("\n") else "\n", flush=True)
    if cp.returncode != 0:
        raise RuntimeError("ARCHITECTURE_LINT=FAIL")
    emit("ARCHITECTURE_LINT", "PASS")
    return {"returncode": 0}


def get_runtime_state(base_url: str) -> dict:
    status, _, _ = http_json("GET", f"{base_url}/health", timeout=15)
    if status != 200:
        raise RuntimeError(f"FASTAPI_HEALTH=FAIL status={status}")
    emit("FASTAPI_HEALTH", "PASS")

    _, cosmos, _ = http_json("GET", f"{base_url}/demo/cosmos-runtime", timeout=15)
    if cosmos.get("version") != "p3a2-v1" or cosmos.get("data_plane") is not True:
        raise RuntimeError(f"COSMOS_RUNTIME=FAIL payload={cosmos}")
    emit("COSMOS_RUNTIME", "PASS p3a2-v1")

    _, grounding, _ = http_json("GET", f"{base_url}/demo/grounding-runtime", timeout=15)
    if grounding.get("version") != "v6" or grounding.get("ask_guard_wrapped") is not True:
        raise RuntimeError(f"GROUNDING_RUNTIME=FAIL payload={grounding}")
    emit("GROUNDING_RUNTIME", "PASS v6")

    _, sync, _ = http_json(
        "POST",
        f"{base_url}/demo/powerbi-sync",
        body={},
        timeout=90,
    )
    if sync.get("status") != "PASS":
        raise RuntimeError(f"POWERBI_SNAPSHOT_SYNC=FAIL payload={sync}")

    try:
        count = int(sync["ai_request_count"])
    except Exception as exc:
        raise RuntimeError(f"POWERBI_AI_REQUEST_COUNT_PARSE=FAIL payload={sync}") from exc

    emit("POWERBI_SNAPSHOT_SYNC", "PASS")
    emit("AI_REQUESTS_CURRENT", count)

    teams_report_path = ROOT / "results/latest/p3b-teams-live-e2e.json"
    teams_report = json.loads(teams_report_path.read_text(encoding="utf-8-sig"))
    if (
        teams_report.get("status") != "PASS"
        or teams_report.get("component_status") != "Implemented"
        or teams_report.get("live_tenant_e2e") != "PASS"
    ):
        raise RuntimeError(f"TEAMS_PRIOR_LIVE_E2E=FAIL payload={teams_report}")
    emit("TEAMS_PRIOR_LIVE_E2E", "PASS")

    return {
        "ai_request_count": count,
        "cosmos": cosmos,
        "grounding": grounding,
        "teams_report": {
            "status": teams_report.get("status"),
            "component_status": teams_report.get("component_status"),
            "live_tenant_e2e": teams_report.get("live_tenant_e2e"),
        },
    }


def live_regression(base_url: str, before_count: int) -> dict:
    session_id = f"main-regression-{uuid.uuid4()}"
    user_id = "techscope-main-regression"
    question = (
        "What role does Azure Databricks play in TechScope? "
        "Include authoritative technology IDs and citations."
    )

    emit("MAIN_LIVE_REGRESSION", "START")
    emit("MAIN_LIVE_REGRESSION_SESSION", session_id)
    emit("AI_REQUESTS_BEFORE_REGRESSION", before_count)

    status, answer, headers = http_json(
        "POST",
        f"{base_url}/ask",
        body={"question": question},
        headers={
            "X-TechScope-Session-Id": session_id,
            "X-TechScope-User-Id": user_id,
            "X-TechScope-Channel": "regression",
        },
        timeout=240,
    )

    if status != 200:
        raise RuntimeError(f"MAIN_LIVE_ASK=FAIL status={status}")

    grounded = answer.get("grounded") is True
    citations = answer.get("citations") if isinstance(answer.get("citations"), list) else []
    technology_ids = (
        answer.get("grounded_technology_ids")
        if isinstance(answer.get("grounded_technology_ids"), list)
        else []
    )
    cosmos_persisted = headers.get("x-techscope-cosmos-persisted", "").lower() == "true"
    interaction_id = headers.get("x-techscope-interaction-id", "")

    if not grounded:
        raise RuntimeError(f"MAIN_LIVE_GROUNDED=FAIL payload={answer}")
    if not citations:
        raise RuntimeError(f"MAIN_LIVE_CITATIONS=FAIL payload={answer}")
    if not technology_ids:
        raise RuntimeError(f"MAIN_LIVE_TECHNOLOGY_IDS=FAIL payload={answer}")
    if not cosmos_persisted:
        raise RuntimeError(
            "MAIN_LIVE_COSMOS_PERSISTED=FAIL "
            f"header={headers.get('x-techscope-cosmos-persisted')}"
        )

    emit("MAIN_LIVE_ASK", "PASS")
    emit("MAIN_LIVE_GROUNDED", "PASS")
    emit("MAIN_LIVE_CITATIONS", len(citations))
    emit("MAIN_LIVE_TECHNOLOGY_IDS", len(technology_ids))
    emit("MAIN_LIVE_COSMOS_PERSISTED", "PASS")

    # Session GET is a direct runtime persistence verification.
    session_status, session_payload, _ = http_json(
        "GET",
        f"{base_url}/cosmos/session/{quote(session_id, safe='')}",
        timeout=60,
    )
    if session_status != 200:
        raise RuntimeError(f"MAIN_LIVE_COSMOS_SESSION=FAIL status={session_status}")
    emit("MAIN_LIVE_COSMOS_SESSION", "PASS")

    deadline = time.monotonic() + 120
    after_count = None
    final_sync: dict = {}
    while time.monotonic() < deadline:
        _, final_sync, _ = http_json(
            "POST",
            f"{base_url}/demo/powerbi-sync",
            body={},
            timeout=90,
        )
        if final_sync.get("status") == "PASS":
            try:
                candidate = int(final_sync["ai_request_count"])
            except Exception:
                candidate = -1
            if candidate >= before_count + 1:
                after_count = candidate
                break
        time.sleep(3)

    if after_count is None:
        raise RuntimeError(
            f"MAIN_LIVE_SQL_DELTA=FAIL before={before_count} sync={final_sync}"
        )
    if after_count != before_count + 1:
        raise RuntimeError(
            f"MAIN_LIVE_SQL_DELTA=FAIL expected={before_count + 1} actual={after_count}"
        )

    emit("AI_REQUESTS_AFTER_REGRESSION", after_count)
    emit("MAIN_LIVE_SQL_DELTA", "PASS +1")
    emit("MAIN_LIVE_POWERBI_SNAPSHOT", "PASS")

    return {
        "question": question,
        "session_id": session_id,
        "interaction_id": interaction_id,
        "grounded": grounded,
        "citation_count": len(citations),
        "technology_id_count": len(technology_ids),
        "cosmos_persisted": cosmos_persisted,
        "session_get_status": session_status,
        "ai_requests_before": before_count,
        "ai_requests_after": after_count,
        "sql_increment": after_count - before_count,
        "powerbi_snapshot_sync": "PASS",
    }


def write_report(
    *,
    env_name: str,
    state: dict,
    prior: dict,
    live: dict | None,
    tracked_count: int,
) -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "PASS",
        "stage": "MAIN_FULL_REGRESSION",
        "runtime_cli": MARKER,
        "environment": env_name,
        "canonical_command": "python tools/techscope.py all --env dev",
        "fastapi": "PASS",
        "cosmos": "PASS",
        "grounding": "PASS",
        "teams_prior_live_e2e": "PASS",
        "powerbi_snapshot_sync": "PASS",
        "architecture_lint": "PASS",
        "git_tracked_secret_path_scan": "PASS",
        "prior_artifacts": prior,
        "tracked_file_count": tracked_count,
        "ai_requests_current": state["ai_request_count"],
        "live_regression": live,
        "release_ready": False,
        "release_blocker": "FULL_REBOOT_COLD_START_VALIDATION_PENDING",
    }
    path = RESULT_DIR / "main-full-regression.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit("MAIN_REGRESSION_REPORT", str(path.relative_to(ROOT)).replace("\\", "/"))
    return path


def command_all(args: argparse.Namespace) -> int:
    emit("TECHSCOPE_RUNTIME_CLI", MARKER)
    emit("TECHSCOPE_ENV", args.env)
    emit("MAIN_REGRESSION", "START")

    prior = verify_prior_evidence()
    tracked = verify_tracked_secret_paths()
    state = get_runtime_state(args.base_url)
    live = None

    if args.live_regression:
        live = live_regression(args.base_url, state["ai_request_count"])

    architecture_lint()

    write_report(
        env_name=args.env,
        state=state,
        prior=prior,
        live=live,
        tracked_count=len(tracked),
    )

    emit("MAIN_FULL_REGRESSION", "PASS")
    emit("RELEASE_READY", "NO")
    emit("RELEASE_BLOCKER", "FULL_REBOOT_COLD_START_VALIDATION_PENDING")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TechScope canonical runtime CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    all_cmd = sub.add_parser("all")
    all_cmd.add_argument("--env", default="dev", choices=["dev"])
    all_cmd.add_argument("--base-url", default=DEFAULT_BASE_URL)
    all_cmd.add_argument("--live-regression", action="store_true")
    all_cmd.set_defaults(func=command_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
