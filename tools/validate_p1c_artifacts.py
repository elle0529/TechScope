#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def fail(m): print("P1C_ARTIFACT_VALIDATION=FAIL "+m); raise SystemExit(1)
def main():
    sql=ROOT/"sql/00_schema.sql"; tmdl=ROOT/"powerbi/model/TechScope_Model.tmdl"
    dax=ROOT/"powerbi/model/measures.dax"; bp=ROOT/"powerbi/report/report-blueprint.json"
    for f in [sql,tmdl,dax,bp,ROOT/"adf/PL_Ingest_TechScope.json",ROOT/"databricks/src/01_build_techscope.py"]:
        if not f.exists(): fail("missing="+str(f.relative_to(ROOT)))
    s=sql.read_text(encoding="utf-8-sig")
    for x in ["DimTechnology","DimCategory","DimCompany","DimArchitecture","FactTechnologyRelation",
              "FactCompanyTechnology","FactAIInteraction","vwTechnologyOverview","vwCategorySummary",
              "vwAIInteractionSummary","FOREIGN KEY","CREATE OR ALTER VIEW"]:
        if x not in s: fail("sql_token="+x)
    for x in ["DimTechnology","DimCategory","DimCompany","DimArchitecture","FactTechnologyRelation",
              "FactCompanyTechnology","FactAIInteraction"]:
        if f"OBJECT_ID(N'techscope.{x}',N'U') IS NULL" not in s: fail("sql_idempotency="+x)
    t=tmdl.read_text(encoding="utf-8-sig")
    for x in ["createOrReplace","ref table TechnologyOverview","ref table CategorySummary",
              "ref table AIInteractionSummary","measure 'Technology Count'","measure 'Grounding Rate'"]:
        if x not in t: fail("tmdl_token="+x)
    d=dax.read_text(encoding="utf-8-sig")
    for x in ["Technology Count :=","Total Relations :=","Grounding Rate :="]:
        if x not in d: fail("dax="+x)
    b=json.loads(bp.read_text(encoding="utf-8-sig"))
    if b.get("status")!="source_blueprint_only" or len(b.get("pages",[]))!=3: fail("blueprint_contract")
    print("AZURE_SQL_SOURCE_CONTRACT=PASS")
    print("POWER_BI_SOURCE_CONTRACT=PASS")
    print("P1B_UPSTREAM_CONTRACT=PASS")
    print("P1C_ARTIFACT_VALIDATION=PASS")
    return 0
if __name__=="__main__": raise SystemExit(main())
