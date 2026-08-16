from pathlib import Path
import json

root=Path("/workspaces/TechScope/powerbi/demo")
report=root/"TechScopeDemo.Report"
sem=root/"TechScopeDemo.SemanticModel"

required=[
    root/"TechScopeDemo.pbip",
    report/"definition.pbir",
    report/"definition/version.json",
    report/"definition/report.json",
    report/"definition/pages/pages.json",
    sem/"definition.pbism",
    sem/"definition/database.tmdl",
    sem/"definition/model.tmdl",
]
for p in required:
    if not p.exists():
        raise RuntimeError(f"Missing: {p}")

for p in report.rglob("*.json"):
    json.loads(p.read_text(encoding="utf-8"))

pages=json.loads((report/"definition/pages/pages.json").read_text(encoding="utf-8"))
if len(pages.get("pageOrder",[]))!=3:
    raise RuntimeError("Expected exactly 3 visible demo pages")

visuals=list((report/"definition/pages").glob("*/visuals/*/visual.json"))
if len(visuals)<9:
    raise RuntimeError(f"Expected >=9 visuals, got {len(visuals)}")

tmdl="\n".join(p.read_text(encoding="utf-8") for p in sem.rglob("*.tmdl"))
for token in [
    "Technology Count","Category Count","Company Count","Direct Claims",
    "Indirect Claims","Architecture Layers","Technology Hierarchy",
    "AI Requests","Success Rate","Citation Rate","Average AI Latency (ms)"
]:
    if token not in tmdl:
        raise RuntimeError("Missing semantic model token: "+token)

print("POWER_BI_PBIP_STRUCTURE=PASS")
print(f"POWER_BI_DEMO_PAGE_COUNT={len(pages['pageOrder'])}")
print(f"POWER_BI_DEMO_VISUAL_COUNT={len(visuals)}")
print("POWER_BI_SEMANTIC_ACCEPTANCE_FIELDS=PASS")
