#!/usr/bin/env python3
"""TechScope canonical restartable automation orchestrator.

Canonical:
    python tools/techscope.py all --env dev

The orchestrator never treats an unimplemented or externally blocked cloud
stage as success. Local development may continue while ZERO_INTERVENTION_READY
is not PASS, but cloud-mutating steps are gated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
LATEST = RESULTS / "latest"
RUNS = RESULTS / "runs"
STATE_PATH = RESULTS / "bootstrap-state.json"

CANONICAL_STEPS = [
    "preflight",
    "lint",
    "plan",
    "provision",
    "deploy",
    "seed",
    "run-main",
    "run-skill-proof",
    "verify",
    "collect-evidence",
    "sync-docs",
    "report",
]

CLOUD_MUTATING_STEPS = {
    "provision",
    "deploy",
    "seed",
    "run-main",
    "run-skill-proof",
}

TOOLCHAIN_COMMANDS = [
    "python",
    "uv",
    "node",
    "pnpm",
    "az",
    "bicep",
    "databricks",
    "sqlpackage",
    "atk",
    "git",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def simple_yaml(path: Path) -> dict[str, Any]:
    """Minimal parser for the repository's nested scalar-only config."""
    data: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, data)]

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        key, value = raw.strip().split(":", 1)
        value = value.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        current = stack[-1][1]

        if not value:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
            continue

        low = value.lower()
        if low == "null":
            parsed: Any = None
        elif low == "true":
            parsed = True
        elif low == "false":
            parsed = False
        elif (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            parsed = value[1:-1]
        else:
            parsed = value

        current[key] = parsed

    return data


@dataclass
class StepResult:
    status: str
    detail: str
    artifacts: list[str]
    returncode: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "artifacts": self.artifacts,
            "returncode": self.returncode,
        }


class Orchestrator:
    def __init__(self, env: str, command: str, stop_after: str | None = None) -> None:
        self.env = env
        self.command = command
        self.stop_after = stop_after
        self.config_path = ROOT / "config" / f"techscope.{env}.yaml"
        self.run_id = (
            datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        self.run_dir = RUNS / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        LATEST.mkdir(parents=True, exist_ok=True)

        self.manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "command": command,
            "environment": env,
            "started_at": now_iso(),
            "cwd": str(ROOT),
            "python": sys.version.split()[0],
            "steps": {},
            "status": "RUNNING",
            "scope": "local orchestrator state; live cloud claims require actual step evidence",
        }
        self.config: dict[str, Any] = {}

    def save_manifest(self) -> None:
        self.manifest["updated_at"] = now_iso()
        write_json(self.run_dir / "run-manifest.json", self.manifest)
        write_json(LATEST / "run-manifest.json", self.manifest)

    def save_state(self, last_completed: str | None, next_step: str | None, status: str) -> None:
        state = {
            "environment": self.env,
            "run_id": self.run_id,
            "status": status,
            "last_completed_step": last_completed,
            "next_step": next_step,
            "updated_at": now_iso(),
            "steps": self.manifest["steps"],
        }
        write_json(STATE_PATH, state)

    def summary(self, status: str, next_step: str | None, detail: str) -> None:
        lines = [
            "# TechScope Latest Summary",
            "",
            f"timestamp: {now_iso()}",
            f"run_id: {self.run_id}",
            f"command: {self.command}",
            f"environment: {self.env}",
            f"status: {status}",
            f"detail: {detail}",
            f"next_step: {next_step or 'NONE'}",
            "",
            "Primary details:",
            "- results/latest/run-manifest.json",
            "- results/latest/manual-actions.md",
        ]
        write_text(LATEST / "summary.md", "\n".join(lines) + "\n")

    def clear_manual_actions(self) -> None:
        write_text(
            LATEST / "manual-actions.md",
            "# Manual Actions\n\nNone for the completed local stage.\n",
        )

    def manual_gate(self, blocked_step: str, reason: str, where: str, action: str, verify: str) -> None:
        text = "\n".join(
            [
                "# Manual Actions",
                "",
                f"blocked_step: {blocked_step}",
                f"reason: {reason}",
                f"where_to_fix: {where}",
                f"exact_manual_action: {action}",
                f"how_to_verify: {verify}",
                f"resume_command: python tools/techscope.py resume --env {self.env}",
                "",
            ]
        )
        write_text(LATEST / "manual-actions.md", text)

    def run_subprocess(self, argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )

    def step_preflight(self) -> StepResult:
        started = time.monotonic()
        required = [
            self.config_path,
            ROOT / "source" / "rawdata.md",
            ROOT / "docs" / "status.md",
            ROOT / "docs" / "architecture.md",
            ROOT / "docs" / "evidence.md",
            ROOT
            / "docs"
            / "baselines"
            / "TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md",
        ]
        missing_files = [
            str(p.relative_to(ROOT)) for p in required if not p.exists()
        ]
        missing_tools = [cmd for cmd in TOOLCHAIN_COMMANDS if shutil.which(cmd) is None]

        if missing_files or missing_tools:
            return StepResult(
                "FAIL",
                f"missing_files={missing_files}; missing_tools={missing_tools}",
                [],
                1,
            )

        self.config = simple_yaml(self.config_path)
        elapsed = time.monotonic() - started
        artifact = self.run_dir / "preflight.json"
        write_json(
            artifact,
            {
                "passed": True,
                "elapsed_seconds": round(elapsed, 3),
                "config": str(self.config_path.relative_to(ROOT)),
                "source": "source/rawdata.md",
                "toolchain": TOOLCHAIN_COMMANDS,
            },
        )
        return StepResult("PASS", f"preflight {elapsed:.2f}s", [str(artifact.relative_to(ROOT))])

    def step_lint(self) -> StepResult:
        cp = self.run_subprocess(
            [sys.executable, "tools/architecture_lint.py", "--json"],
            timeout=60,
        )
        artifact = self.run_dir / "architecture-lint.json"

        try:
            parsed = json.loads(cp.stdout)
        except json.JSONDecodeError:
            parsed = {
                "passed": False,
                "stdout": cp.stdout,
                "stderr": cp.stderr,
                "returncode": cp.returncode,
            }

        write_json(artifact, parsed)

        if cp.returncode != 0:
            return StepResult(
                "FAIL",
                "Architecture lint failed",
                [str(artifact.relative_to(ROOT))],
                cp.returncode or 1,
            )

        return StepResult(
            "PASS",
            "Baseline CHECK 01-25 passed",
            [str(artifact.relative_to(ROOT))],
        )

    def step_plan(self) -> StepResult:
        if not self.config:
            self.config = simple_yaml(self.config_path)

        runtime = self.config.get("runtime", {})
        allow_cloud = bool(runtime.get("allow_cloud_mutation", False))

        plan = {
            "environment": self.env,
            "allow_cloud_mutation": allow_cloud,
            "steps": [],
        }

        for step in CANONICAL_STEPS:
            if step in {"preflight", "lint", "plan"}:
                action = "run-local"
            elif step in CLOUD_MUTATING_STEPS and not allow_cloud:
                action = "blocked-by-cloud-mutation-gate"
            else:
                module = ROOT / "automation" / "steps" / f"{step}.py"
                action = "run-implementation" if module.exists() else "implementation-pending"
            plan["steps"].append({"step": step, "action": action})

        artifact = LATEST / "plan.json"
        write_json(artifact, plan)
        write_json(self.run_dir / "plan.json", plan)
        return StepResult("PASS", "Execution plan generated", [str(artifact.relative_to(ROOT))])

    def zero_intervention_ready(self) -> tuple[bool, str]:
        if not self.config:
            self.config = simple_yaml(self.config_path)

        allow_cloud = bool(self.config.get("runtime", {}).get("allow_cloud_mutation", False))
        readiness_candidates = [
            RESULTS / "bootstrap-readiness.json",
            RESULTS / "latest" / "bootstrap-readiness.json",
        ]

        readiness = None
        for path in readiness_candidates:
            if path.exists():
                try:
                    readiness = json.loads(path.read_text(encoding="utf-8-sig"))
                    break
                except Exception:
                    pass

        ready_value = None
        if isinstance(readiness, dict):
            ready_value = (
                readiness.get("ZERO_INTERVENTION_READY")
                or readiness.get("zero_intervention_ready")
                or readiness.get("status")
            )

        passed = allow_cloud and str(ready_value).upper() == "PASS"
        detail = f"allow_cloud_mutation={allow_cloud}; readiness={ready_value!r}"
        return passed, detail

    def external_step(self, step: str) -> StepResult:
        module = ROOT / "automation" / "steps" / f"{step}.py"
        if not module.exists():
            return StepResult(
                "BLOCKED",
                f"Implementation module not present: {module.relative_to(ROOT)}",
                [],
                30,
            )

        cp = self.run_subprocess(
            [
                sys.executable,
                str(module.relative_to(ROOT)),
                "--env",
                self.env,
                "--run-id",
                self.run_id,
            ],
            timeout=1800,
        )
        log = self.run_dir / f"{step}.log"
        write_text(
            log,
            "STDOUT\n"
            + cp.stdout
            + "\nSTDERR\n"
            + cp.stderr
            + f"\nRETURN_CODE={cp.returncode}\n",
        )

        return StepResult(
            "PASS" if cp.returncode == 0 else "FAIL",
            f"{step} implementation returned {cp.returncode}",
            [str(log.relative_to(ROOT))],
            cp.returncode,
        )

    def step_report(self) -> StepResult:
        artifact = LATEST / "summary.md"
        return StepResult("PASS", "Report output maintained by orchestrator", [str(artifact.relative_to(ROOT))])

    def execute(self, start_index: int = 0) -> int:
        last_completed: str | None = None
        self.clear_manual_actions()
        self.save_manifest()

        for index in range(start_index, len(CANONICAL_STEPS)):
            step = CANONICAL_STEPS[index]
            next_step = CANONICAL_STEPS[index + 1] if index + 1 < len(CANONICAL_STEPS) else None

            if step in CLOUD_MUTATING_STEPS:
                ready, readiness_detail = self.zero_intervention_ready()
                if not ready:
                    result = StepResult(
                        "BLOCKED",
                        f"ZERO_INTERVENTION_READY != PASS ({readiness_detail})",
                        ["results/latest/manual-actions.md"],
                        20,
                    )
                    self.manifest["steps"][step] = result.as_dict()
                    self.manifest["status"] = "BLOCKED"
                    self.save_manifest()
                    self.save_state(last_completed, step, "BLOCKED")
                    self.manual_gate(
                        blocked_step=step,
                        reason="Cloud mutation is gated until ZERO_INTERVENTION_READY=PASS.",
                        where="TechScope bootstrap readiness automation / external cloud prerequisites",
                        action="Complete the generated cloud-readiness bootstrap stage; do not manually provision TechScope resources one-by-one.",
                        verify="bootstrap-readiness.json reports ZERO_INTERVENTION_READY=PASS and config runtime.allow_cloud_mutation is true.",
                    )
                    self.summary("BLOCKED", step, result.detail)
                    print(f"STEP={step} STATUS=BLOCKED")
                    print("ZERO_INTERVENTION_READY=NOT_READY")
                    print("MANUAL_ACTIONS=results/latest/manual-actions.md")
                    return 20

            if step == "preflight":
                result = self.step_preflight()
            elif step == "lint":
                result = self.step_lint()
            elif step == "plan":
                result = self.step_plan()
            elif step == "report":
                result = self.step_report()
            else:
                result = self.external_step(step)

            self.manifest["steps"][step] = result.as_dict()
            self.save_manifest()
            print(f"STEP={step} STATUS={result.status} DETAIL={result.detail}")

            if result.status != "PASS":
                self.manifest["status"] = result.status
                self.save_manifest()
                self.save_state(last_completed, step, result.status)

                if result.status == "BLOCKED":
                    self.manual_gate(
                        blocked_step=step,
                        reason=result.detail,
                        where=f"automation/steps/{step}.py",
                        action=f"Implement the missing {step} automation unit, then run resume.",
                        verify=f"automation/steps/{step}.py exists and exits 0 for the requested environment.",
                    )

                self.summary(result.status, step, result.detail)
                return result.returncode or 1

            last_completed = step
            self.save_state(last_completed, next_step, "RUNNING")

            if self.stop_after == step:
                self.manifest["status"] = "STOPPED_AFTER_REQUESTED_STEP"
                self.save_manifest()
                self.save_state(last_completed, next_step, "STOPPED_AFTER_REQUESTED_STEP")
                self.summary("PASS", next_step, f"Stopped after requested step {step}")
                self.clear_manual_actions()
                print(f"ORCHESTRATION_LOCAL_VALIDATION=PASS STOP_AFTER={step}")
                return 0

        self.manifest["status"] = "PASS"
        self.manifest["completed_at"] = now_iso()
        self.save_manifest()
        self.save_state(last_completed, None, "PASS")
        self.summary("PASS", None, "Canonical all sequence completed")
        self.clear_manual_actions()
        print("TECHSCOPE_ALL=PASS")
        return 0


def resume_command(env: str) -> int:
    if not STATE_PATH.exists():
        print("RESUME=FAIL")
        print("No results/bootstrap-state.json exists.")
        return 1

    state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    next_step = state.get("next_step")
    if not next_step:
        print("RESUME=NOOP")
        print("No pending step.")
        return 0

    if next_step not in CANONICAL_STEPS:
        print(f"RESUME=FAIL unknown next_step={next_step}")
        return 1

    runner = Orchestrator(env=env, command="resume")
    return runner.execute(start_index=CANONICAL_STEPS.index(next_step))


def release_command(env: str) -> int:
    LATEST.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [sys.executable, "tools/architecture_lint.py", "--release", "--json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )

    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {
            "passed": False,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
            "returncode": cp.returncode,
        }

    write_json(LATEST / "release-lint.json", payload)
    status = "PASS" if cp.returncode == 0 else "FAIL"
    write_text(
        LATEST / "summary.md",
        "\n".join(
            [
                "# TechScope Latest Summary",
                "",
                f"timestamp: {now_iso()}",
                "command: release",
                f"environment: {env}",
                f"status: {status}",
                "result: results/latest/release-lint.json",
                "",
                "Portfolio Ready additionally requires Scenario A-D acceptance.",
                "",
            ]
        ),
    )
    print(f"RELEASE_LINT={status}")
    return cp.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="techscope")
    sub = parser.add_subparsers(dest="command", required=True)

    all_cmd = sub.add_parser("all", help="Run the canonical automation sequence")
    all_cmd.add_argument("--env", default="dev")
    all_cmd.add_argument("--stop-after", choices=CANONICAL_STEPS, default=None)

    resume = sub.add_parser("resume", help="Resume from the recorded pending step")
    resume.add_argument("--env", default="dev")

    release = sub.add_parser("release", help="Run machine-checkable release lint")
    release.add_argument("--env", default="dev")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "all":
        return Orchestrator(args.env, "all", args.stop_after).execute()
    if args.command == "resume":
        return resume_command(args.env)
    if args.command == "release":
        return release_command(args.env)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
