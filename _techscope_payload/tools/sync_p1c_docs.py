#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]; STATUS=ROOT/"docs/status.md"; EVIDENCE=ROOT/"docs/evidence.md"
ITEMS=[("CMP_AZURE_SQL","Azure SQL","EVD-AZURE-SQL-001","sql/00_schema.sql"),
       ("CMP_POWER_BI","Power BI","EVD-POWER-BI-001","powerbi/model/TechScope_Model.tmdl")]
def evidence(eid,cid,loc):
    txt=EVIDENCE.read_text(encoding="utf-8-sig")
    if eid in txt:return
    lines=txt.splitlines(); sep=None
    for i,l in enumerate(lines):
        if l.strip().startswith("|") and "Evidence ID" in l and "Component ID" in l: sep=i+1; break
    if sep is None: raise RuntimeError("Evidence table not found")
    k=sep+1
    while k<len(lines) and lines[k].strip().startswith("|"):k+=1
    lines.insert(k,f"| {eid} | {cid} | SOURCE | {loc} |")
    EVIDENCE.write_text("\n".join(lines)+"\n",encoding="utf-8")
def status(cid,name):
    txt=STATUS.read_text(encoding="utf-8-sig")
    pat=re.compile(rf"^(\|\s*{re.escape(cid)}\s*\|\s*{re.escape(name)}\s*\|\s*MAIN\s*\|\s*REQUIRED\s*\|)\s*"
                   r"(Planned|In Progress|Prototype|Implemented|Blocked)\s*(\|)\s*$",re.M)
    m=list(pat.finditer(txt))
    if len(m)!=1: raise RuntimeError(f"{cid} row cardinality={len(m)}")
    cur=m[0].group(2)
    if cur in ("Prototype","Implemented"): print(f"{cid}_STATUS=REUSED_{cur.upper()}"); return
    STATUS.write_text(pat.sub(r"\1 In Progress \3",txt,count=1),encoding="utf-8")
    print(f"{cid}_STATUS=In_Progress")
def main():
    for cid,name,eid,loc in ITEMS:
        if not (ROOT/loc).exists(): raise RuntimeError("missing "+loc)
        evidence(eid,cid,loc); status(cid,name)
    print("P1C_DOC_SYNC=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
