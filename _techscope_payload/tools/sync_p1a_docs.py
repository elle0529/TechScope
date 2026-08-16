#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "status.md"
EVIDENCE = ROOT / "docs" / "evidence.md"
MANIFEST = ROOT / "extractor" / "output" / "manifest.json"
RUN_EVIDENCE = ROOT / "evidence" / "python" / "extractor-run.json"

def ensure_evidence_row(eid: str, etype: str, location: str) -> None:
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
    lines.insert(insert_at, f"| {eid} | CMP_PYTHON | {etype} | {location} |")
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def update_status() -> None:
    text = STATUS.read_text(encoding="utf-8-sig")
    pattern = re.compile(
        r"^(\|\s*CMP_PYTHON\s*\|\s*Python Extractor\s*\|\s*MAIN\s*\|\s*REQUIRED\s*\|)\s*"
        r"(Planned|In Progress|Prototype|Implemented|Blocked)\s*(\|)\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"CMP_PYTHON status row cardinality={len(matches)}")
    current = matches[0].group(2)
    if current == "Implemented":
        print("CMP_PYTHON_STATUS=REUSED_IMPLEMENTED")
        return
    text = pattern.sub(r"\1 Prototype \3", text, count=1)
    STATUS.write_text(text, encoding="utf-8")
    print("CMP_PYTHON_STATUS=Prototype")

def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    if not manifest.get("source_unchanged"):
        raise RuntimeError("Source immutability proof failed")

    for name in [
        "technology.csv","category.csv","relation.csv",
        "company_usecase.csv","architecture_mapping.csv"
    ]:
        item = manifest["outputs"].get(name)
        if not item:
            raise RuntimeError(f"Manifest output missing: {name}")
        path = ROOT / item["path"]
        if not path.exists():
            raise RuntimeError(f"Output missing: {path}")

    RUN_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    RUN_EVIDENCE.write_text(
        json.dumps({
            "component": "CMP_PYTHON",
            "status": "PASS",
            "mode": "LOCAL_PROTOTYPE",
            "command": "python extractor/extract.py",
            "manifest": "extractor/output/manifest.json",
            "source_unchanged": True,
            "outputs": manifest["outputs"],
            "claim_boundary": "Local structural extraction prototype; ADLS-integrated runtime is not claimed.",
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ensure_evidence_row("EVD-PYTHON-001", "SOURCE", "extractor/extract.py")
    ensure_evidence_row("EVD-PYTHON-002", "EXECUTION", "evidence/python/extractor-run.json")
    update_status()
    print("P1A_DOC_SYNC=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
