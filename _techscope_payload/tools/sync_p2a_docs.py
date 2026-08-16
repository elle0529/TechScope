#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/status.md"
EVIDENCE = ROOT / "docs/evidence.md"

ITEMS = [
    ("CMP_AI_SEARCH", "Azure AI Search", "EVD-AI-SEARCH-001", "rag/search-index.template.json"),
    ("CMP_AZURE_OPENAI", "Azure OpenAI", "EVD-AZURE-OPENAI-001", "backend/app/azure_openai_adapter.py"),
    ("CMP_FASTAPI", "FastAPI", "EVD-FASTAPI-001", "backend/app/main.py"),
]


def ensure_evidence(eid: str, cid: str, location: str) -> None:
    text = EVIDENCE.read_text(encoding="utf-8-sig")
    if eid in text:
        return

    lines = text.splitlines()
    sep = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "Evidence ID" in line and "Component ID" in line:
            sep = i + 1
            break
    if sep is None:
        raise RuntimeError("Evidence table not found")

    insert = sep + 1
    while insert < len(lines) and lines[insert].strip().startswith("|"):
        insert += 1

    lines.insert(insert, f"| {eid} | {cid} | SOURCE | {location} |")
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_in_progress(cid: str, name: str) -> None:
    text = STATUS.read_text(encoding="utf-8-sig")
    pattern = re.compile(
        rf"^(\|\s*{re.escape(cid)}\s*\|\s*{re.escape(name)}\s*\|\s*MAIN\s*\|\s*REQUIRED\s*\|)\s*"
        r"(Planned|In Progress|Prototype|Implemented|Blocked)\s*(\|)\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"{cid} status row cardinality={len(matches)}")

    current = matches[0].group(2)
    if current in {"Prototype", "Implemented"}:
        print(f"{cid}_STATUS=REUSED_{current.upper()}")
        return

    STATUS.write_text(
        pattern.sub(r"\1 In Progress \3", text, count=1),
        encoding="utf-8",
    )
    print(f"{cid}_STATUS=In_Progress")


def main() -> int:
    for cid, name, eid, location in ITEMS:
        if not (ROOT / location).exists():
            raise RuntimeError(f"Source artifact missing: {location}")
        ensure_evidence(eid, cid, location)
        set_in_progress(cid, name)

    print("P2A_DOC_SYNC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
