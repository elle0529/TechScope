#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

RUN_ID = "323321120939012"
ROOT = Path("/workspaces/TechScope")
OUT = ROOT / "results/latest/p1e-serverless-failure-diagnostic.json"


def run_json(cmd):
    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED: "
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-4000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-4000:]
        )
    text = (cp.stdout or "").strip()
    if not text:
        return {}
    return json.loads(text)


def trim(value, limit=12000):
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= limit else s[:limit] + "\n...[TRUNCATED]..."


def main():
    print("P1E_SERVERLESS_FAILURE_DIAGNOSTIC=START", flush=True)
    print(f"PARENT_RUN_ID={RUN_ID}", flush=True)

    parent = run_json(
        ["databricks", "jobs", "get-run", RUN_ID, "-o", "json"]
    )
    tasks = parent.get("tasks") or []
    if not tasks:
        raise RuntimeError("PARENT_RUN_HAS_NO_TASKS")

    task = tasks[0]
    task_run_id = str(task.get("run_id") or "")
    if not task_run_id:
        raise RuntimeError("TASK_RUN_ID_MISSING")

    print(f"TASK_RUN_ID={task_run_id}", flush=True)
    print(
        "TASK_STATE="
        + str((task.get("state") or {}).get("life_cycle_state")),
        flush=True,
    )
    print(
        "TASK_RESULT="
        + str((task.get("state") or {}).get("result_state")),
        flush=True,
    )

    output = run_json(
        [
            "databricks",
            "jobs",
            "get-run-output",
            task_run_id,
            "-o",
            "json",
        ]
    )

    notebook_output = output.get("notebook_output") or {}
    metadata = output.get("metadata") or {}
    error = output.get("error")
    error_trace = output.get("error_trace")
    logs = output.get("logs")
    logs_truncated = output.get("logs_truncated")

    report = {
        "parent_run_id": RUN_ID,
        "task_run_id": task_run_id,
        "task_state": task.get("state"),
        "parent_state": parent.get("state"),
        "output_error": trim(error),
        "output_error_trace": trim(error_trace, 20000),
        "output_logs": trim(logs, 20000),
        "logs_truncated": logs_truncated,
        "notebook_output": notebook_output,
        "metadata": metadata,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("GET_RUN_OUTPUT=PASS", flush=True)

    if error:
        print("----- NOTEBOOK ERROR START -----", flush=True)
        print(trim(error, 8000), flush=True)
        print("----- NOTEBOOK ERROR END -----", flush=True)

    if error_trace:
        print("----- ERROR TRACE START -----", flush=True)
        print(trim(error_trace, 12000), flush=True)
        print("----- ERROR TRACE END -----", flush=True)

    if logs:
        print("----- TASK LOGS START -----", flush=True)
        print(trim(logs, 12000), flush=True)
        print("----- TASK LOGS END -----", flush=True)

    result = notebook_output.get("result")
    if result:
        print("----- NOTEBOOK RESULT START -----", flush=True)
        print(trim(result, 8000), flush=True)
        print("----- NOTEBOOK RESULT END -----", flush=True)

    print(
        "REPORT=results/latest/p1e-serverless-failure-diagnostic.json",
        flush=True,
    )
    print("DATA_MUTATION=NO", flush=True)
    print("NEXT_ACTION=SEND_CONSOLE_OUTPUT", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
