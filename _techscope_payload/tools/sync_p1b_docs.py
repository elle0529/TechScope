#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "status.md"
EVIDENCE = ROOT / "docs" / "evidence.md"

UPDATES = {
    "CMP_ADF": {
        "component": "Azure Data Factory",
        "status": "In Progress",
        "evidence": ("EVD-ADF-001", "SOURCE", "adf/PL_Ingest_TechScope.json"),
    },
    "CMP_DATABRICKS": {
        "component": "Azure Databricks",
        "status": "In Progress",
        "evidence": ("EVD-DATABRICKS-001", "SOURCE", "databricks/src/01_build_techscope.py"),
    },
}

def update_status(component_id: str, component: str, target_status: str) -> None:
    text = STATUS.read_text(encoding="utf-8-sig")
    pattern = re.compile(
        rf"^(\|\s*{re.escape(component_id)}\s*\|\s*{re.escape(component)}\s*\|\s*MAIN\s*\|\s*REQUIRED\s*\|)\s*"
        r"(Planned|In Progress|Prototype|Implemented|Blocked)\s*(\|)\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"{component_id} status row cardinality={len(matches)}")
    current = matches[0].group(2)
    if current in {"Prototype", "Implemented"}:
        print(f"{component_id}_STATUS=REUSED_{current.replace(' ', '_').upper()}")
        return
    text = pattern.sub(rf"\1 {target_status} \3", text, count=1)
    STATUS.write_text(text, encoding="utf-8")
    print(f"{component_id}_STATUS={target_status.replace(' ', '_')}")

def ensure_evidence(eid: str, component_id: str, etype: str, location: str) -> None:
    text = EVIDENCE.read_text(encoding="utf-8-sig")
    if eid in text:
        return
    lines = text.splitlines()
    sep = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "Evidence ID" in line and "Component ID" in line:
            if i + 1 < len(lines):
                sep = i + 1
            break
    if sep is None:
        raise RuntimeError("Evidence table not found")
    insert_at = sep + 1
    while insert_at < len(lines) and lines[insert_at].strip().startswith("|"):
        insert_at += 1
    lines.insert(insert_at, f"| {eid} | {component_id} | {etype} | {location} |")
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main() -> int:
    for component_id, info in UPDATES.items():
        eid, etype, location = info["evidence"]
        if not (ROOT / location).exists():
            raise RuntimeError(f"Source artifact missing: {location}")
        ensure_evidence(eid, component_id, etype, location)
        update_status(component_id, info["component"], info["status"])

    print("P1B_DOC_SYNC=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
