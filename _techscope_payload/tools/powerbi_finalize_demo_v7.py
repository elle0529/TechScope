from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path("/workspaces/TechScope/powerbi")
SOURCE = ROOT / "demo_snapshot"
FINAL = ROOT / "demo_final"

if not SOURCE.exists():
    raise RuntimeError(f"Snapshot source not found: {SOURCE}")

if FINAL.exists():
    shutil.rmtree(FINAL)
shutil.copytree(SOURCE, FINAL)

REPORT = FINAL / "TechScopeDemo.Report"
PAGES = REPORT / "definition" / "pages"

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def save(path: Path, obj: dict) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

def column(table: str, prop: str) -> dict:
    return {
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": prop,
            }
        },
        "queryRef": f"{table}.{prop}",
        "nativeQueryRef": prop,
    }

def measure(table: str, prop: str) -> dict:
    return {
        "field": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": prop,
            }
        },
        "queryRef": f"{table}.{prop}",
        "nativeQueryRef": prop,
    }

def set_card(path: Path, fields: list[tuple[str, str]]) -> None:
    obj = load(path)
    obj["visual"]["query"] = {
        "queryState": {
            "Data": {
                "projections": [measure(t, m) for t, m in fields]
            }
        }
    }
    save(path, obj)

def set_table(path: Path, fields: list[tuple[str, str]]) -> None:
    obj = load(path)
    obj["visual"]["query"] = {
        "queryState": {
            "Values": {
                "projections": [column(t, c) for t, c in fields]
            }
        }
    }
    save(path, obj)

def set_slicer(path: Path, table: str, field: str, title: str) -> None:
    obj = load(path)
    obj["visual"]["query"] = {
        "queryState": {
            "Values": {
                "projections": [column(table, field)]
            }
        }
    }
    obj["visual"]["objects"] = {
        "data": [{
            "properties": {
                "mode": {"expr": {"Literal": {"Value": "'Dropdown'"}}}
            }
        }],
        "header": [{
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
            }
        }],
    }
    save(path, obj)

page1 = PAGES / "ReportSection000000000000000000000001" / "visuals"
page2 = PAGES / "ReportSection000000000000000000000002" / "visuals"

set_card(
    page1 / "10000000000000000001" / "visual.json",
    [
        ("ExecutiveSummary", "Technology Count"),
        ("ExecutiveSummary", "Category Count"),
        ("ExecutiveSummary", "AI Requests"),
        ("ExecutiveSummary", "Success Rate"),
        ("ExecutiveSummary", "Citation Rate"),
        ("ExecutiveSummary", "Average AI Latency (ms)"),
    ],
)

set_table(
    page1 / "10000000000000000002" / "visual.json",
    [
        ("TechnologyExplorer", "TechnologyId"),
        ("TechnologyExplorer", "TechnologyName"),
        ("TechnologyExplorer", "CategoryName"),
        ("TechnologyExplorer", "SourceId"),
    ],
)

set_slicer(
    page2 / "20000000000000000001" / "visual.json",
    "TechnologyExplorer",
    "CategoryName",
    "Category",
)

set_slicer(
    page2 / "20000000000000000002" / "visual.json",
    "TechnologyExplorer",
    "SourceId",
    "Source",
)

# Remove unsupported Architecture/Evidence slicer from the final demo.
obsolete = page2 / "20000000000000000003"
if obsolete.exists():
    shutil.rmtree(obsolete)

set_table(
    page2 / "20000000000000000004" / "visual.json",
    [
        ("TechnologyExplorer", "CategoryName"),
        ("TechnologyExplorer", "TechnologyId"),
        ("TechnologyExplorer", "TechnologyName"),
        ("TechnologyExplorer", "SourceId"),
    ],
)

# Rename the visible page to accurately describe what is proven.
page2_json = (
    PAGES
    / "ReportSection000000000000000000000002"
    / "page.json"
)
p2 = load(page2_json)
p2["displayName"] = "02 Technology Catalog"
save(page2_json, p2)

# Ensure the report no longer visibly references unresolved fields.
visible_json = "\n".join(
    p.read_text(encoding="utf-8")
    for p in REPORT.rglob("*.json")
)

# TMDL may still contain these fields as source columns; only PBIR visible
# projections must be clean.
for forbidden in (
    '"queryRef": "TechnologyExplorer.ArchitectureLayer"',
    '"queryRef": "TechnologyExplorer.EvidenceType"',
    '"queryRef": "ExecutiveSummary.Company Count"',
    '"queryRef": "ExecutiveSummary.Direct Claims"',
    '"queryRef": "ExecutiveSummary.Indirect Claims"',
    '"queryRef": "ExecutiveSummary.Architecture Layers"',
):
    if forbidden in visible_json:
        raise RuntimeError("Unresolved visible field remains: " + forbidden)

print("POWER_BI_FINAL_COPY=PASS")
print("POWER_BI_FINAL_PAGE_1=PROVEN_KPI_ONLY")
print("POWER_BI_FINAL_PAGE_2=TECHNOLOGY_CATALOG")
print("POWER_BI_FINAL_PAGE_3=AI_OPERATIONS_UNCHANGED")
print("UNRESOLVED_KPI_VISIBLE=NO")
print("UNMAPPED_ARCHITECTURE_VISIBLE=NO")
print("FAKE_VALUES_INSERTED=NO")
print("POWER_BI_FINAL_PATCH=PASS")
