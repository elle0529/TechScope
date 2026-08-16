#!/usr/bin/env python3
from __future__ import annotations
import csv, json, subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/workspaces/TechScope")
OUT = ROOT / "results" / "latest" / "p1e-relation-diagnostic.json"
SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"
TERMS = (
    "FactTechnologyRelation","fact_technology_relation","technology_relation",
    "relation.csv","source_technology","target_technology",
)
SCAN_DIRS = [ROOT/"tools", ROOT/"databricks", ROOT/"sql", ROOT/"extractor", ROOT/"generated"]
TEXT_SUFFIXES = {".py",".sql",".json",".md",".txt",".yaml",".yml",".csv"}

def sample_csv(path: Path):
    out={"path":str(path.relative_to(ROOT)),"exists":path.exists()}
    if not path.exists(): return out
    try:
        with path.open("r",encoding="utf-8-sig",newline="") as f:
            r=csv.DictReader(f); headers=list(r.fieldnames or [])
            rows=[]; count=0
            for row in r:
                count += 1
                if len(rows)<5: rows.append({k:row.get(k) for k in headers})
        out.update(headers=headers,row_count=count,sample_rows=rows)
    except Exception as e:
        out["error"]=f"{type(e).__name__}: {e}"
    return out

def locate_relation_files():
    found=[]
    for p in ROOT.rglob("*relation*.csv"):
        if p.is_file():
            found.append(sample_csv(p))
    return found[:30]

def locate_gold_relation_artifacts():
    found=[]
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        full=str(p).lower()
        if ("fact_technology_relation" in full or "technology_relation" in full) and p.suffix.lower() in {".csv",".json",".jsonl",".parquet"}:
            found.append(str(p.relative_to(ROOT)))
    return found[:50]

def code_references():
    matches=[]
    for d in SCAN_DIRS:
        if not d.exists(): continue
        for p in d.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES: continue
            try: text=p.read_text(encoding="utf-8",errors="ignore")
            except Exception: continue
            for n,line in enumerate(text.splitlines(),1):
                if any(t.lower() in line.lower() for t in TERMS):
                    matches.append({"path":str(p.relative_to(ROOT)),"line":n,"text":line.strip()[:500]})
                    if len(matches)>=120: return matches
    return matches

def run_optional(cmd, timeout=20):
    try:
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False)
        return {"returncode":cp.returncode,"stdout":(cp.stdout or "").strip()[:8000],"stderr":(cp.stderr or "").strip()[:3000]}
    except Exception as e:
        return {"error":f"{type(e).__name__}: {e}"}

def sql_diagnostic():
    from mssql_python import connect
    cs=(f"Server={SQL_SERVER};Database={SQL_DATABASE};Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;TrustServerCertificate=no;")
    result={}
    conn=connect(cs)
    try:
        cur=conn.cursor()
        cur.execute("""
            SELECT s.name,t.name
            FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
            WHERE t.name LIKE '%Technology%' OR t.name LIKE '%Relation%'
               OR t.name LIKE '%Evidence%' OR t.name LIKE '%Source%'
            ORDER BY s.name,t.name
        """)
        result["related_tables"]=[{"schema":r[0],"table":r[1]} for r in cur.fetchall()]

        def table_info(schema,table):
            cur.execute("""
                SELECT c.column_id,c.name,TYPE_NAME(c.user_type_id),c.max_length,c.is_nullable,c.is_identity
                FROM sys.columns c
                JOIN sys.tables t ON t.object_id=c.object_id
                JOIN sys.schemas s ON s.schema_id=t.schema_id
                WHERE s.name=? AND t.name=?
                ORDER BY c.column_id
            """,(schema,table))
            cols=[{"ordinal":r[0],"name":r[1],"type":r[2],"max_length":r[3],
                   "nullable":bool(r[4]),"identity":bool(r[5])} for r in cur.fetchall()]
            if not cols: return {"exists":False,"columns":[]}
            cur.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{table}]")
            return {"exists":True,"columns":cols,"row_count":int(cur.fetchone()[0])}

        result["FactTechnologyRelation"]=table_info("techscope","FactTechnologyRelation")
        result["DimTechnology"]=table_info("techscope","DimTechnology")
        result["DimCategory"]=table_info("techscope","DimCategory")

        cur.execute("""
            SELECT s.name,v.name FROM sys.views v
            JOIN sys.schemas s ON s.schema_id=v.schema_id
            WHERE v.name LIKE '%Relation%' OR v.name LIKE '%Technology%'
            ORDER BY s.name,v.name
        """)
        result["related_views"]=[{"schema":r[0],"view":r[1]} for r in cur.fetchall()]
        return result
    finally:
        conn.close()

def infer_next_path(report):
    fact=report.get("sql",{}).get("FactTechnologyRelation",{})
    nonempty=[r for r in report.get("relation_files",[]) if isinstance(r.get("row_count"),int) and r["row_count"]>0]
    gold=report.get("gold_relation_artifacts",[])
    if not fact.get("exists"): return "CREATE_CANONICAL_FACT_SCHEMA_THEN_DATABRICKS_NORMALIZE_LOAD"
    if fact.get("row_count",0)>0: return "RELATION_FACT_ALREADY_NONEMPTY_VERIFY_ONLY"
    if gold: return "VERIFY_EXISTING_GOLD_RELATION_THEN_LOAD_AZURE_SQL"
    if nonempty: return "DATABRICKS_NORMALIZE_RESOLVE_IDS_BUILD_GOLD_THEN_LOAD_AZURE_SQL"
    return "UPSTREAM_RELATION_EXTRACTION_OR_ADLS_LINEAGE_REPAIR_REQUIRED"

def main():
    report={
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "mutation":False,
        "relation_files":locate_relation_files(),
        "gold_relation_artifacts":locate_gold_relation_artifacts(),
        "code_references":code_references(),
    }
    print("P1E_RELATION_DIAGNOSTIC=START",flush=True)
    try:
        report["sql"]=sql_diagnostic()
        print("AZURE_SQL_INTROSPECTION=PASS",flush=True)
    except Exception as e:
        report["sql_error"]=f"{type(e).__name__}: {e}"
        print("AZURE_SQL_INTROSPECTION=FAIL",flush=True)
        print(report["sql_error"],flush=True)

    report["databricks_current_user"]=run_optional(["databricks","current-user","me","-o","json"],20)
    report["databricks_jobs"]=run_optional(["databricks","jobs","list","-o","json"],25)
    report["recommended_repair_path"]=infer_next_path(report)

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

    nonempty=[r for r in report["relation_files"] if isinstance(r.get("row_count"),int) and r["row_count"]>0]
    fact=report.get("sql",{}).get("FactTechnologyRelation",{})
    print(f"RELATION_CSV_FILES={len(report['relation_files'])}",flush=True)
    print(f"RELATION_NONEMPTY_FILES={len(nonempty)}",flush=True)
    for r in nonempty[:5]:
        print(f"RELATION_SOURCE={r['path']} ROWS={r['row_count']} HEADERS={','.join(r.get('headers',[]))}",flush=True)
    print("FACT_TECHNOLOGY_RELATION_EXISTS="+("YES" if fact.get("exists") else "NO"),flush=True)
    print("FACT_TECHNOLOGY_RELATION_ROWS="+str(fact.get("row_count","UNKNOWN")),flush=True)
    print("GOLD_RELATION_ARTIFACTS="+str(len(report["gold_relation_artifacts"])),flush=True)
    print("REPAIR_PATH="+report["recommended_repair_path"],flush=True)
    print("REPORT=results/latest/p1e-relation-diagnostic.json",flush=True)
    print("DATA_MUTATION=NO",flush=True)
    print("NEXT_ACTION=SEND_CONSOLE_OUTPUT",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
