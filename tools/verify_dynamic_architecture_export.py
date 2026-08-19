#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

OUT="docs/portfolio/TechScope_Dynamic_Architecture_Portfolio.md"
RESULT="results/latest/dynamic-architecture-export.json"
DIAGS=(
 "docs/portfolio/diagrams/01_dynamic_architecture_3layer.mmd",
 "docs/portfolio/diagrams/02_current_as_built_architecture.mmd",
 "docs/portfolio/diagrams/03_ai_operations_feedback_loop.mmd",
)
MARKERS=(
 "# TechScope Dynamic Architecture Portfolio",
 "## 2. Dynamic Architecture — 3 Layer Model",
 "## 3. Current As-Built Architecture",
 "## 4. AI Operations Feedback Loop",
 "## 7. Component Status",
 "## 8. Evidence Model",
 "## 12. Source Integrity Manifest",
 "## 13. Export Contract",
)

def root_from(start):
 for c in [start.resolve(),*start.resolve().parents]:
  if (c/"docs/status.md").exists() and (c/"docs/architecture.md").exists(): return c
 p=Path(r"C:\TechScope")
 if p.exists(): return p
 raise FileNotFoundError("TechScope root not found")

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--repo-root"); a=ap.parse_args()
 root=root_from(Path(a.repo_root) if a.repo_root else Path.cwd()); fail=[]
 out=root/OUT
 text=out.read_text(encoding="utf-8-sig",errors="replace") if out.exists() else ""
 if not out.exists(): fail.append("portfolio_missing")
 for m in MARKERS:
  if m not in text: fail.append("marker:"+m)
 for rel in DIAGS:
  p=root/rel
  if not p.exists() or p.stat().st_size==0: fail.append("diagram:"+rel)
 rp=root/RESULT
 try: res=json.loads(rp.read_text(encoding="utf-8-sig"))
 except Exception: res={}; fail.append("result_json_invalid_or_missing")
 if res.get("status")!="PASS": fail.append("export_status_not_pass")
 if res.get("frozen_baseline_unchanged") is not True: fail.append("frozen_baseline_not_verified")
 if fail:
  for x in fail: print("VERIFY_FAIL="+x)
  print("DYNAMIC_ARCHITECTURE_EXPORT_VERIFY=FAIL"); return 1
 print(f"REPO_ROOT={root}"); print(f"PORTFOLIO_FILE={OUT}"); print("PORTFOLIO_MARKERS=PASS"); print("DIAGRAM_FILES=PASS"); print("EXPORT_RESULT=PASS"); print("FROZEN_BASELINE_UNCHANGED=PASS"); print("DYNAMIC_ARCHITECTURE_EXPORT_VERIFY=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
