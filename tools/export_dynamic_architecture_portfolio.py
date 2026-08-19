#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("docs/status.md","docs/architecture.md","docs/evidence.md")
OUT = "docs/portfolio/TechScope_Dynamic_Architecture_Portfolio.md"
DDIR = "docs/portfolio/diagrams"
RESULT = "results/latest/dynamic-architecture-export.json"
FROZEN_RX = re.compile(r"(baseline.*final.*frozen|final.*frozen.*baseline)", re.I)

def now():
    return datetime.now(timezone.utc).isoformat()

def read(p):
    return p.read_text(encoding="utf-8-sig", errors="replace")

def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""):
            h.update(c)
    return h.hexdigest()

def root_of(start):
    s=start.resolve()
    for c in [s]+list(s.parents):
        if all((c/x).exists() for x in REQUIRED):
            return c
    c=Path(r"C:\TechScope")
    if c.exists() and all((c/x).exists() for x in REQUIRED):
        return c
    raise FileNotFoundError("TechScope repository root not found")

def frozen_files(root):
    found=[]
    candidates=[]
    try:
        for p in root.iterdir():
            try:
                if p.is_file():
                    candidates.append(p)
            except OSError:
                pass
    except OSError:
        pass

    for sub in ("docs","architecture"):
        b=root/sub
        if not b.exists():
            continue
        for dp,dns,fns in os.walk(b,topdown=True,followlinks=False):
            dns[:] = [d for d in dns if d not in {
                ".git",".venv","venv","node_modules","__pycache__","dist","build","results"
            }]
            for fn in fns:
                candidates.append(Path(dp)/fn)

    seen=set()
    for p in candidates:
        try:
            rel=str(p.relative_to(root)).replace("\\","/")
            if not (FROZEN_RX.search(p.name) or FROZEN_RX.search(rel)):
                continue
            key=str(p.resolve(strict=False)).lower()
            if key in seen:
                continue
            with p.open("rb"):
                pass
            found.append(p)
            seen.add(key)
        except (OSError,PermissionError,ValueError):
            continue
    return sorted(found,key=lambda x:str(x).lower())

def section(text,names):
    lines=text.splitlines()
    heads=[]
    for i,l in enumerate(lines):
        m=re.match(r"^(#{1,6})\s+(.+)$",l)
        if m:
            heads.append((i,len(m.group(1)),m.group(2).strip()))
    for k,(i,lev,title) in enumerate(heads):
        if any(re.search(n,title,re.I) for n in names):
            end=len(lines)
            for j in range(k+1,len(heads)):
                if heads[j][1] <= lev:
                    end=heads[j][0]
                    break
            return "\n".join(lines[i+1:end]).strip()
    return None

def mermaids(text):
    return [x.strip() for x in re.findall(r"```mermaid\s*(.*?)```",text,re.I|re.S) if x.strip()]

def statuses(text):
    out=[]
    lines=text.splitlines()

    for i in range(len(lines)-2):
        if "|" not in lines[i] or "|" not in lines[i+1]:
            continue
        h=[x.strip() for x in lines[i].strip().strip("|").split("|")]
        s=[x.strip() for x in lines[i+1].strip().strip("|").split("|")]
        if len(h)!=len(s) or len(h)<2 or not all(re.fullmatch(r":?-{3,}:?",x) for x in s):
            continue
        hl=[x.lower() for x in h]
        si=next((j for j,x in enumerate(hl) if "status" in x or "상태" in x),None)
        if si is None:
            continue
        ci=next((j for j,x in enumerate(hl) if any(k in x for k in ("component","cmp","구성","항목","name"))),0)
        j=i+2
        while j<len(lines) and "|" in lines[j] and lines[j].strip():
            c=[x.strip() for x in lines[j].strip().strip("|").split("|")]
            if len(c)>=len(h) and c[ci] and c[si]:
                out.append((c[ci],c[si]))
            j+=1

    for l in lines:
        m=re.search(r"\b(CMP_[A-Z0-9_]+)\b",l,re.I)
        if not m:
            continue
        stat=next((w for w in ("Implemented","Prototype","Planned","Deferred","PASS","FAIL","준비") if re.search(re.escape(w),l,re.I)),None)
        if stat:
            out.append((m.group(1).upper(),stat))

    ded=[]
    seen=set()
    for a,b in out:
        k=(a.lower(),b.lower())
        if k not in seen:
            seen.add(k)
            ded.append((a,b))
    return ded

def status_md(rows):
    if not rows:
        return "_No component status rows parsed automatically; authoritative source remains `docs/status.md`._"
    lines=["| Component | Current Status |","|---|---|"]
    for a,b in rows:
        lines.append(f"| {a.replace('|','/')} | {b.replace('|','/')} |")
    return "\n".join(lines)

def d1():
    return '''flowchart BT
    L0["L0 · Actual Implementation<br/>Code · Infra · Data · Runtime"]
    L1["L1 · Current / Target Architecture Model<br/>Current · Target · Track · ADR"]
    L2["L2 · Architecture Validation<br/>Status · Evidence · Lint · Integrity"]
    L0 -->|"Reflect actual state"| L1
    L1 -->|"Validate consistency"| L2
    L2 -->|"PASS / FAIL feedback"| L0
'''

def d2(status,arch):
    h=(status+"\n"+arch).lower()
    def has(*xs):
        return any(x.lower() in h for x in xs)

    n=[]
    e=[]
    chain=[]

    for nid,label,terms in [
        ("SRC","Source Markdown",("cmp_source","source markdown")),
        ("PY","Python Extractor",("cmp_python","python extractor")),
        ("ADF","Azure Data Factory",("cmp_adf","azure data factory")),
        ("ADLS","ADLS Gen2",("cmp_adls","adls gen2","data lake storage")),
        ("DBX","Azure Databricks",("cmp_databricks","databricks")),
        ("SQL","Azure SQL<br/>Serving / Data Mart",("cmp_azure_sql","azure sql","sqldb"))
    ]:
        if has(*terms):
            n.append(f'    {nid}["{label}"]')
            chain.append(nid)

    for a,b in zip(chain,chain[1:]):
        e.append(f"    {a} --> {b}")

    if has("power bi","powerbi","cmp_power_bi"):
        n.append('    PBI["Power BI<br/>Analytics / AI Operations"]')
        if "SQL" in chain:
            e.append("    SQL --> PBI")

    if has("azure ai search","ai search","cmp_ai_search"):
        n.append('    SEARCH["Azure AI Search"]')
        if "DBX" in chain:
            e.append("    DBX --> SEARCH")

    if has("azure openai","cmp_azure_openai"):
        n.append('    AOAI["Azure OpenAI<br/>RAG / Grounding / Citation"]')
        if has("azure ai search","ai search","cmp_ai_search"):
            e.append("    SEARCH --> AOAI")

    if has("fastapi","cmp_fastapi","/ask"):
        n.append('    API["FastAPI<br/>/ask"]')
        if has("azure openai","cmp_azure_openai"):
            e.append("    AOAI --> API")

    if has("web ui","web interface","frontend"):
        n.append('    WEB["Web UI"]')
        if has("fastapi","cmp_fastapi","/ask"):
            e.append("    WEB --> API")

    if has("teams","cmp_teams"):
        n.append('    TEAMS["Microsoft Teams"]')
        if has("fastapi","cmp_fastapi","/ask"):
            e.append("    TEAMS --> API")

    if has("factairequest","ai request"):
        n.append('    FACT["FactAIRequest<br/>Status · Latency · Citation · Grounding"]')
        if has("fastapi","cmp_fastapi","/ask"):
            e.append("    API --> FACT")

    if has("autosync","runtime_data","powerbi_runtime_sync"):
        n.append('    SYNC["Runtime Snapshot AutoSync"]')
        if has("factairequest","ai request"):
            e.append("    FACT --> SYNC")
        if has("power bi","powerbi","cmp_power_bi"):
            e.append("    SYNC --> PBI")

    if not n:
        n=['    A["No current components detected automatically"]']

    return "flowchart LR\n"+"\n".join(n+e)+"\n"

def d3():
    return '''flowchart LR
    U["User Question"] --> UI["Web UI / Teams"]
    UI --> API["FastAPI /ask"]
    API --> RAG["Azure AI Search + Azure OpenAI<br/>RAG"]
    RAG --> ANS["Grounded Answer + Citation"]
    API --> FACT["FactAIRequest<br/>Status · Latency · Citation · Grounding"]
    FACT --> SYNC["Runtime Snapshot AutoSync"]
    SYNC --> PBI["Power BI Import<br/>Manual Refresh"]
    PBI --> OPS["AI Operations Analytics"]
'''

def mb(code):
    return "```mermaid\n"+code.rstrip()+"\n```"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",default=None)
    ap.add_argument("--output",default=OUT)
    ap.add_argument("--diagram-dir",default=DDIR)
    ap.add_argument("--result",default=RESULT)
    ap.add_argument("--strict",action="store_true")
    a=ap.parse_args()

    try:
        root=root_of(Path(a.repo_root) if a.repo_root else Path.cwd())
    except Exception as ex:
        print(f"EXPORTER_REPO_ROOT=FAIL {ex}",file=sys.stderr)
        return 2

    miss=[x for x in REQUIRED if not (root/x).exists()]
    if miss:
        print("REQUIRED_SOURCE_DOCS=FAIL "+",".join(miss),file=sys.stderr)
        return 3

    frozen=frozen_files(root)
    before={str(p.relative_to(root)).replace("\\","/"):sha(p) for p in frozen}

    st=read(root/"docs/status.md")
    ar=read(root/"docs/architecture.md")
    ev=read(root/"docs/evidence.md")

    rows=statuses(st)
    mms=mermaids(ar)
    cur=section(ar,(r"\bcurrent\b",r"현재.*architecture"))
    tgt=section(ar,(r"\btarget\b",r"목표.*architecture"))

    x1=d1()
    x2=d2(st,ar)
    x3=d3()

    dd=root/a.diagram_dir
    dd.mkdir(parents=True,exist_ok=True)

    for fn,code in [
        ("01_dynamic_architecture_3layer.mmd",x1),
        ("02_current_as_built_architecture.mmd",x2),
        ("03_ai_operations_feedback_loop.mmd",x3)
    ]:
        (dd/fn).write_text(code.rstrip()+"\n",encoding="utf-8")

    counts={k:len(re.findall(rf"\b{k}\b",ev,re.I)) for k in ("SOURCE","EXECUTION","OUTPUT")}

    srcdiag="\n\n".join(
        f"### Source Diagram {i}\n\n{mb(c)}"
        for i,c in enumerate(mms,1)
    ) or "_No Mermaid blocks found in `docs/architecture.md`._"

    manifest="\n".join(
        f"- `{r}` — SHA-256 `{sha(root/r)}` — {(root/r).stat().st_size:,} bytes"
        for r in REQUIRED
    )

    doc=f'''# TechScope Dynamic Architecture Portfolio

> Generated automatically from the current TechScope Source of Truth.  
> Generated UTC: `{now()}`

## 1. Purpose

TechScope uses Dynamic Architecture so architecture documentation follows the verified implementation state rather than becoming an isolated static artifact.

## 2. Dynamic Architecture — 3 Layer Model

{mb(x1)}

## 3. Current As-Built Architecture

{mb(x2)}

## 4. AI Operations Feedback Loop

{mb(x3)}

## 5. Current Architecture — Source of Truth Excerpt

{cur or "_Current section was not parsed automatically; authoritative source remains `docs/architecture.md`._"}

## 6. Target Architecture — Source of Truth Excerpt

{tgt or "_Target section was not parsed automatically; authoritative source remains `docs/architecture.md`._"}

## 7. Component Status

{status_md(rows)}

## 8. Evidence Model

| Evidence Type | Occurrences |
|---|---:|
| SOURCE | {counts["SOURCE"]} |
| EXECUTION | {counts["EXECUTION"]} |
| OUTPUT | {counts["OUTPUT"]} |

```text
Actual Implementation
  -> Evidence
  -> Component Status
  -> Current Architecture
  -> Validation / PASS or FAIL
```

## 9. Architecture Diagrams Already Defined in Source of Truth

{srcdiag}

## 10. Generated Diagram Files

- `{a.diagram_dir}/01_dynamic_architecture_3layer.mmd`
- `{a.diagram_dir}/02_current_as_built_architecture.mmd`
- `{a.diagram_dir}/03_ai_operations_feedback_loop.mmd`

## 11. Generated Result

- `{a.result}`

## 12. Source Integrity Manifest

{manifest}

Frozen Baseline candidates checked: **{len(frozen)}**

## 13. Export Contract

**Authoritative inputs**
- `docs/status.md`
- `docs/architecture.md`
- `docs/evidence.md`

**Safety**
- Frozen Baseline documents are read-only.
- Source of Truth documents are read-only.
- Azure resources are neither created nor deleted.
- Secrets are not persisted.
'''

    op=root/a.output
    op.parent.mkdir(parents=True,exist_ok=True)
    op.write_text(doc,encoding="utf-8")

    after={str(p.relative_to(root)).replace("\\","/"):sha(p) for p in frozen}
    frozen_ok=(before==after)

    sf=[]
    if a.strict:
        if not rows: sf.append("component_status")
        if not mms: sf.append("source_mermaid")
        if cur is None: sf.append("current_section")
        if tgt is None: sf.append("target_section")

    result={
        "schema":"techscope.dynamic-architecture-export.v1",
        "timestamp_utc":now(),
        "status":"PASS" if frozen_ok and not sf else "FAIL",
        "repository_root":str(root),
        "output":a.output,
        "diagram_dir":a.diagram_dir,
        "parsed_component_status_rows":len(rows),
        "source_architecture_mermaid_blocks":len(mms),
        "evidence_occurrences":counts,
        "frozen_baseline_files_checked":len(frozen),
        "frozen_baseline_unchanged":frozen_ok,
        "strict_failures":sf,
        "generated_files":[
            a.output,
            f"{a.diagram_dir}/01_dynamic_architecture_3layer.mmd",
            f"{a.diagram_dir}/02_current_as_built_architecture.mmd",
            f"{a.diagram_dir}/03_ai_operations_feedback_loop.mmd"
        ]
    }

    rp=root/a.result
    rp.parent.mkdir(parents=True,exist_ok=True)
    rp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    if not frozen_ok:
        print("FROZEN_BASELINE_UNCHANGED=FAIL",file=sys.stderr)
        return 8

    if sf:
        print("EXPORT_STRICT=FAIL "+",".join(sf),file=sys.stderr)
        return 9

    print(f"REPO_ROOT={root}")
    print("REQUIRED_SOURCE_DOCS=PASS")
    print(f"PARSED_COMPONENT_STATUS_ROWS={len(rows)}")
    print(f"SOURCE_ARCHITECTURE_MERMAID_BLOCKS={len(mms)}")
    print(f"FROZEN_BASELINE_FILES_CHECKED={len(frozen)}")
    print("FROZEN_BASELINE_UNCHANGED=PASS")
    print(f"PORTFOLIO_OUTPUT={a.output}")
    print(f"RESULT_OUTPUT={a.result}")
    print("DYNAMIC_ARCHITECTURE_EXPORT=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
