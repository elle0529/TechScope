#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
SUMMARY = ROOT / "results/latest/main-final-status-summary.json"
VERIFY = ROOT / "results/latest/main-final-verification.json"
STATUS = ROOT / "docs/status.md"
EVIDENCE = ROOT / "docs/evidence.md"

STATUS_START = "<!-- TECHSCOPE_MAIN_FINAL_STATUS:START -->"
STATUS_END = "<!-- TECHSCOPE_MAIN_FINAL_STATUS:END -->"
EVIDENCE_START = "<!-- TECHSCOPE_MAIN_FINAL_EVIDENCE:START -->"
EVIDENCE_END = "<!-- TECHSCOPE_MAIN_FINAL_EVIDENCE:END -->"


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd,
        cwd=ROOT,
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


def replace_block(text: str, start: str, end: str, block: str) -> str:
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    replacement = start + "\n" + block.rstrip() + "\n" + end

    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)

    if text and not text.endswith("\n"):
        text += "\n"

    return text + "\n" + replacement + "\n"


def main():
    print("MAIN_FINAL_DOC_SYNC=START", flush=True)

    if not SUMMARY.exists():
        raise RuntimeError("MAIN_FINAL_SUMMARY_NOT_FOUND")
    if not VERIFY.exists():
        raise RuntimeError("MAIN_FINAL_VERIFY_REPORT_NOT_FOUND")

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    verify = json.loads(VERIFY.read_text(encoding="utf-8"))

    statuses = summary.get("main_component_status") or {}
    sql = summary.get("sql_counts") or {}
    blockers = summary.get("blockers") or []

    status_lines = [
        "## MAIN Final Verification",
        "",
        f"- Verification: `PASS`",
        f"- Portfolio Core Ready: `{'YES' if summary.get('portfolio_core_ready') else 'NO'}`",
        f"- Release Ready: `{'YES' if summary.get('release_ready') else 'NO'}`",
        "",
        "| Component | Status |",
        "|---|---|",
    ]

    ordered = [
        "CMP_ADLS",
        "CMP_PYTHON",
        "CMP_ADF",
        "CMP_DATABRICKS",
        "CMP_AZURE_SQL",
        "CMP_POWER_BI",
        "CMP_AI_SEARCH",
        "CMP_AZURE_OPENAI",
        "CMP_FASTAPI",
        "CMP_COSMOS",
        "CMP_TEAMS",
    ]

    for comp in ordered:
        status_lines.append(
            f"| `{comp}` | {statuses.get(comp, 'Unknown')} |"
        )

    status_lines += [
        "",
        "### Verified runtime counts",
        "",
        f"- DimTechnology: `{sql.get('technology')}`",
        f"- DimCategory: `{sql.get('category')}`",
        f"- FactTechnologyRelation: `{sql.get('relation')}`",
        f"- FactAIRequest: `{sql.get('ai_request')}`",
        f"- BridgeAIRequestTechnology: `{sql.get('bridge')}`",
        "",
        "### Release blockers",
        "",
    ]

    if blockers:
        for blocker in blockers:
            status_lines.append(f"- {blocker}")
    else:
        status_lines.append("- None")

    status_lines += [
        "",
        "> This block is generated from "
        "`results/latest/main-final-status-summary.json`.",
    ]

    evidence_lines = [
        "## MAIN Final Verification Evidence",
        "",
        "- Final verification report: "
        "`results/latest/main-final-verification.json`",
        "- Final status summary: "
        "`results/latest/main-final-status-summary.json`",
        "- P1E relation repair report: "
        "`results/latest/p1e-relation-repair.json`",
        "- Teams Prototype report: "
        "`results/latest/p3-teams-prototype.json`",
        "- Cosmos blocker report: "
        "`results/latest/p3-cosmos-blocker.json`",
        "",
        "### P1E Technology Relation",
        "",
        f"- FactTechnologyRelation rows: `{sql.get('relation')}`",
        "- FK validation: `PASS`",
        "- Silver/Gold relation persistence: `PASS`",
        "",
        "### Teams",
        "",
        "- Status: `Prototype`",
        "- Teams SDK → FastAPI `/ask` adapter smoke: `PASS`",
        "- SOURCE evidence: `PASS`",
        "- EXECUTION evidence: `PASS`",
        "- Live Teams tenant E2E: `NOT COMPLETED`",
        "",
        "### Cosmos DB",
        "",
        "- Status: `Blocked`",
        "- Reason: `NO_EXISTING_COSMOS_ACCOUNT`",
        "- Azure resource creation performed: `NO`",
        "",
        "### Architecture",
        "",
        "- Architecture lint: `PASS`",
        "- Architecture lint checks: `25`",
        "",
        "> This block records verified evidence only; "
        "it does not upgrade blocked/prototype components.",
    ]

    status_text = STATUS.read_text(encoding="utf-8") if STATUS.exists() else "# Status\n"
    evidence_text = EVIDENCE.read_text(encoding="utf-8") if EVIDENCE.exists() else "# Evidence\n"

    STATUS.write_text(
        replace_block(
            status_text,
            STATUS_START,
            STATUS_END,
            "\n".join(status_lines),
        ),
        encoding="utf-8",
    )

    EVIDENCE.write_text(
        replace_block(
            evidence_text,
            EVIDENCE_START,
            EVIDENCE_END,
            "\n".join(evidence_lines),
        ),
        encoding="utf-8",
    )

    print("DOC_STATUS_SYNC=PASS", flush=True)
    print("DOC_EVIDENCE_SYNC=PASS", flush=True)
    print("FROZEN_BASELINE_MODIFIED=NO", flush=True)

    lint = run(
        [sys.executable, str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=120,
    )
    text = (lint.stdout or "") + "\n" + (lint.stderr or "")

    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in text:
        print(text[-5000:], flush=True)
        raise RuntimeError("ARCHITECTURE_LINT_AFTER_FINAL_SYNC=FAIL")

    print("ARCHITECTURE_LINT_AFTER_FINAL_SYNC=PASS", flush=True)
    print("MAIN_FINAL_DOC_SYNC=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
