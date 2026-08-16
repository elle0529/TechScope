#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/cloud-target.dev.json"
OUT=ROOT/"results/latest/p1c-cloud-gate.json"

def az(args, timeout=120):
    cp=subprocess.run(["az",*args,"-o","json"],text=True,capture_output=True,timeout=timeout)
    if cp.returncode!=0: return cp.returncode,None,(cp.stderr or cp.stdout).strip()
    try: return 0,json.loads(cp.stdout or "null"),""
    except Exception as e: return 2,None,f"JSON_PARSE_ERROR {e}"

def blob(x): return json.dumps(x,ensure_ascii=False).lower()

def main():
    cfg=json.loads(CFG.read_text(encoding="utf-8-sig"))
    locs=cfg.get("location_preferences",["koreacentral","eastus2","swedencentral"])
    gens=cfg.get("generation_candidate_models",["gpt-4.1-mini","gpt-4o-mini"])
    embs=cfg.get("embedding_candidate_models",["text-embedding-3-small"])
    providers=cfg.get("required_providers",[])
    result={"timestamp":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "mode":"READ_ONLY","cloud_mutation_performed":False,"providers":{},
            "openai_regions":[],"existing_resources":{},"next_blockers":[]}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    print("P1C_CLOUD_GATE_DEEP_PROBE=START")
    code,acct,err=az(["account","show"])
    if code:
        result["azure_auth"]="FAIL"; result["next_blockers"].append("Azure CLI authentication required")
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("AZURE_AUTH=FAIL"); print(f"RESULT={OUT.relative_to(ROOT)}"); return 0
    result["azure_auth"]="PASS"
    result["subscription"]={"id":acct.get("id"),"name":acct.get("name"),"tenantId":acct.get("tenantId")}
    print(f"AZURE_AUTH=PASS SUBSCRIPTION={acct.get('name')}")
    pending=[]
    for ns in providers:
        c,d,e=az(["provider","show","--namespace",ns])
        state=d.get("registrationState") if c==0 and isinstance(d,dict) else "UNKNOWN"
        result["providers"][ns]={"registrationState":state,"query_status":"PASS" if c==0 else "FAIL",
                                 "error":None if c==0 else e[:400]}
        if state!="Registered": pending.append(ns)
    print(f"PROVIDER_REGISTERED={len(providers)-len(pending)}/{len(providers)}")
    inventory={
      "resource_groups":["group","list"],"storage_accounts":["storage","account","list"],
      "data_factories":["datafactory","list"],"databricks_workspaces":["databricks","workspace","list"],
      "sql_servers":["sql","server","list"],"search_services":["search","service","list"],
      "cognitive_accounts":["cognitiveservices","account","list"],"cosmos_accounts":["cosmosdb","list"]
    }
    for key,args in inventory.items():
        c,d,e=az(args)
        result["existing_resources"][key]={"status":"PASS" if c==0 else "PENDING",
          "count":len(d) if c==0 and isinstance(d,list) else None,
          "names":[x.get("name") for x in d if isinstance(x,dict) and x.get("name")][:20] if c==0 and isinstance(d,list) else [],
          "error":None if c==0 else e[:400]}
    usage_visible=False; candidate=None
    for loc in locs:
        print(f"OPENAI_REGION_PROBE={loc}")
        mc,models,me=az(["cognitiveservices","model","list","--location",loc])
        uc,usage,ue=az(["cognitiveservices","usage","list","--location",loc])
        mb=blob(models) if mc==0 else ""
        gf=[m for m in gens if m.lower() in mb]; ef=[m for m in embs if m.lower() in mb]
        if uc==0: usage_visible=True
        result["openai_regions"].append({
          "location":loc,"model_query":"PASS" if mc==0 else "FAIL","model_error":None if mc==0 else me[:500],
          "generation_models_found":gf,"embedding_models_found":ef,
          "usage_query":"PASS" if uc==0 else "FAIL","usage_error":None if uc==0 else ue[:500],
          "usage_count":len(usage) if uc==0 and isinstance(usage,list) else None})
        if candidate is None and gf and ef and uc==0: candidate=loc
    result["quota_visibility"]="PASS" if usage_visible else "PENDING"
    result["azure_openai_candidate"]="DISCOVERY_PASS" if candidate else "PENDING"
    if candidate: result["candidate_region"]=candidate
    if pending: result["next_blockers"].append("Unregistered providers: "+", ".join(pending))
    if not usage_visible:
        result["next_blockers"].append("Azure OpenAI quota visibility unavailable; subscription-level Cognitive Services Usages Reader may be required")
    if not candidate:
        result["next_blockers"].append("No preferred region proved with generation + embedding model visibility and readable quota API")
    result["zero_intervention_ready"]="PENDING_CAPABILITY"
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"AZURE_OPENAI_CANDIDATE={result['azure_openai_candidate']}")
    print(f"QUOTA_VISIBILITY={result['quota_visibility']}")
    print("ZERO_INTERVENTION_READY=PENDING_CAPABILITY")
    print(f"RESULT={OUT.relative_to(ROOT)}")
    print("P1C_CLOUD_GATE_DEEP_PROBE=PASS")
    return 0

if __name__=="__main__": raise SystemExit(main())
