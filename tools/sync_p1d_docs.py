#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "status.md"
EVIDENCE = ROOT / "docs" / "evidence.md"
RESULTS = ROOT / "results" / "latest" / "p1d-component-results.json"

COMPONENTS = {
    "CMP_ADLS": {
        "source": ("EVD-ADLS-001", "infra/bicep/p1-data-rg.bicep"),
        "execution": ("EVD-ADLS-002", "evidence/adls/p1d-deployment.json"),
        "output": ("EVD-ADLS-003", "evidence/adls/p1d-output.json"),
    },
    "CMP_ADF": {
        "source": ("EVD-ADF-001", "adf/PL_Ingest_TechScope.json"),
        "execution": ("EVD-ADF-002", "evidence/adf/p1d-execution.json"),
        "output": ("EVD-ADF-003", "evidence/adf/p1d-output.json"),
    },
    "CMP_DATABRICKS": {
        "source": ("EVD-DATABRICKS-001", "databricks/src/01_build_techscope.py"),
        "execution": ("EVD-DATABRICKS-002", "evidence/databricks/p1d-execution.json"),
        "output": ("EVD-DATABRICKS-003", "evidence/databricks/p1d-output.json"),
    },
    "CMP_AZURE_SQL": {
        "source": ("EVD-AZURE-SQL-001", "sql/00_schema.sql"),
        "execution": ("EVD-AZURE-SQL-002", "evidence/azure-sql/p1d-execution.json"),
        "output": ("EVD-AZURE-SQL-003", "evidence/azure-sql/p1d-output.json"),
    },
}

def ensure_evidence(eid: str, cid: str, etype: str, location: str) -> None:
    if not (ROOT / location).exists():
        raise RuntimeError(f"Evidence path missing: {location}")

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
        raise RuntimeError("Evidence registry table not found")

    insert = sep + 1
    while insert < len(lines) and lines[insert].strip().startswith("|"):
        insert += 1

    lines.insert(insert, f"| {eid} | {cid} | {etype} | {location} |")
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def promote_prototype(cid: str) -> None:
    text = STATUS.read_text(encoding="utf-8-sig")
    pattern = re.compile(
        rf"^(\|\s*{re.escape(cid)}\s*\|[^|]+\|\s*MAIN\s*\|\s*REQUIRED\s*\|)\s*"
        r"(Planned|In Progress|Prototype|Implemented|Blocked)\s*(\|)\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"{cid} status row cardinality={len(matches)}")

    current = matches[0].group(2)
    if current == "Implemented":
        print(f"{cid}_STATUS=REUSED_IMPLEMENTED")
        return
    if current == "Prototype":
        print(f"{cid}_STATUS=REUSED_PROTOTYPE")
        return

    STATUS.write_text(
        pattern.sub(r"\1 Prototype \3", text, count=1),
        encoding="utf-8",
    )
    print(f"{cid}_STATUS=Prototype")

def main() -> int:
    result = json.loads(RESULTS.read_text(encoding="utf-8-sig"))
    components = result.get("components", {})

    for cid, status in components.items():
        if status != "PASS" or cid not in COMPONENTS:
            print(f"{cid}_DOC_SYNC=SKIP_{status}")
            continue

        spec = COMPONENTS[cid]
        for etype, key in [
            ("SOURCE", "source"),
            ("EXECUTION", "execution"),
            ("OUTPUT", "output"),
        ]:
            eid, location = spec[key]
            ensure_evidence(eid, cid, etype, location)

        promote_prototype(cid)

    print("P1D_DOC_SYNC=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
