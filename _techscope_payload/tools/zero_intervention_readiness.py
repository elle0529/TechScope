#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cloud-target.dev.json"
HOST_RESULT = ROOT / "results" / "latest" / "zero-readiness-host.json"
OUT = ROOT / "results" / "latest" / "zero-intervention-readiness.json"
OUT_MD = ROOT / "results" / "latest" / "zero-intervention-readiness.md"
MANUAL = ROOT / "results" / "latest" / "manual-actions.md"

def run(args: list[str], timeout: int = 90, env: dict[str, str] | None = None):
    cp = subprocess.run(args, text=True, capture_output=True, timeout=timeout, env=env)
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()

def az(args: list[str], timeout: int = 90):
    code, out, err = run(["az", *args, "-o", "json"], timeout=timeout)
    if code != 0:
        return code, None, err or out
    try:
        return 0, json.loads(out or "null"), ""
    except json.JSONDecodeError as exc:
        return 2, None, f"JSON_PARSE_ERROR: {exc}"

def lower_blob(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False).lower()

def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))

    providers = (
        cfg.get("required_resource_providers")
        or cfg.get("required_providers")
        or []
    )
    generation = (
        cfg.get("generation_model_candidates")
        or cfg.get("generation_candidate_models")
        or ["gpt-4.1-mini", "gpt-4o-mini"]
    )
    embeddings = (
        cfg.get("embedding_model_candidates")
        or cfg.get("embedding_candidate_models")
        or ["text-embedding-3-small"]
    )
    locations = cfg.get("location_preferences") or ["koreacentral", "eastus2", "swedencentral"]

    result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "mode": "READ_ONLY",
        "cloud_mutation_performed": False,
        "config_contract": {
            "provider_key": "required_resource_providers" if cfg.get("required_resource_providers") is not None else "fallback",
            "generation_key": "generation_model_candidates" if cfg.get("generation_model_candidates") is not None else "fallback",
            "embedding_key": "embedding_model_candidates" if cfg.get("embedding_model_candidates") is not None else "fallback",
            "provider_count": len(providers),
            "generation_candidates": generation,
            "embedding_candidates": embeddings,
            "locations": locations,
        },
        "checks": {},
        "blockers": [],
    }

    print("ZERO_INTERVENTION_DEEP_READINESS=START")
    print(f"CONFIG_PROVIDER_COUNT={len(providers)}")

    # 1. Azure auth
    code, account, err = az(["account", "show"])
    if code != 0 or not isinstance(account, dict):
        result["checks"]["azure_auth"] = {"status": "FAIL", "error": err[:500]}
        result["blockers"].append("Azure CLI authentication")
        finalize(result)
        return 0

    result["checks"]["azure_auth"] = {
        "status": "PASS",
        "subscription": account.get("name"),
        "subscription_id": account.get("id"),
        "tenant_id": account.get("tenantId"),
    }
    print(f"AZURE_AUTH=PASS SUBSCRIPTION={account.get('name')}")

    # 2. Resource providers
    provider_rows = []
    provider_pass = True
    for ns in providers:
        c, data, e = az(["provider", "show", "--namespace", ns])
        state = data.get("registrationState") if c == 0 and isinstance(data, dict) else "UNKNOWN"
        provider_rows.append({"namespace": ns, "registrationState": state, "query_status": "PASS" if c == 0 else "FAIL"})
        if state != "Registered":
            provider_pass = False
    result["checks"]["resource_providers"] = {
        "status": "PASS" if provider_pass and len(providers) > 0 else "PENDING",
        "expected": len(providers),
        "registered": sum(1 for x in provider_rows if x["registrationState"] == "Registered"),
        "items": provider_rows,
    }
    print(
        f"PROVIDER_REGISTERED={result['checks']['resource_providers']['registered']}/{len(providers)}"
    )
    if not provider_pass or not providers:
        result["blockers"].append("Required Azure Resource Provider registration")

    # 3. ARM permission validation — reuses existing read-only readiness template.
    readiness_bicep = ROOT / "infra" / "bicep" / "readiness.bicep"
    arm_status = "PENDING"
    arm_error = None
    if readiness_bicep.exists():
        c, out, e = run(
            [
                "az", "deployment", "sub", "validate",
                "--location", locations[0],
                "--template-file", str(readiness_bicep),
                "--parameters",
                f"location={locations[0]}",
                "validationResourceGroupName=rg-techscope-readiness-validate",
                "--validation-level", "Provider",
                "-o", "json",
            ],
            timeout=180,
        )
        arm_status = "PASS" if c == 0 else "FAIL"
        arm_error = None if c == 0 else (e or out)[:1000]
    result["checks"]["arm_provider_validation"] = {"status": arm_status, "error": arm_error}
    print(f"ARM_PROVIDER_VALIDATION={arm_status}")
    if arm_status != "PASS":
        result["blockers"].append("ARM Provider-level deployment permission validation")

    # 4. Azure OpenAI model visibility + quota visibility
    openai_regions = []
    candidate = None
    usage_visible = False
    for loc in locations:
        print(f"OPENAI_REGION_PROBE={loc}")
        mc, models, me = az(["cognitiveservices", "model", "list", "--location", loc], timeout=120)
        uc, usage, ue = az(["cognitiveservices", "usage", "list", "--location", loc], timeout=120)
        model_blob = lower_blob(models) if mc == 0 else ""
        gf = [m for m in generation if m.lower() in model_blob]
        ef = [m for m in embeddings if m.lower() in model_blob]
        if uc == 0:
            usage_visible = True
        row = {
            "location": loc,
            "model_query": "PASS" if mc == 0 else "FAIL",
            "generation_models_found": gf,
            "embedding_models_found": ef,
            "quota_query": "PASS" if uc == 0 else "FAIL",
            "model_error": None if mc == 0 else me[:500],
            "quota_error": None if uc == 0 else ue[:500],
        }
        openai_regions.append(row)
        if candidate is None and gf and ef and uc == 0:
            candidate = loc

    openai_status = "PASS" if candidate else "PENDING"
    result["checks"]["azure_openai_discovery"] = {
        "status": openai_status,
        "candidate_region": candidate,
        "quota_visibility": "PASS" if usage_visible else "PENDING",
        "regions": openai_regions,
        "minimum_api_call": "NOT_PROVEN",
    }
    print(f"AZURE_OPENAI_DISCOVERY={openai_status}")
    print(f"AZURE_OPENAI_QUOTA_VISIBILITY={'PASS' if usage_visible else 'PENDING'}")
    if openai_status != "PASS":
        result["blockers"].append("Azure OpenAI generation+embedding region/model/quota discovery")
    # Per plan, actual minimum API call is a separate high-risk capability.
    result["blockers"].append("Azure OpenAI minimum API call not yet proven")

    # 5. Databricks existing workspace + real read-only workspace auth probe.
    dc, workspaces, de = az(["databricks", "workspace", "list"], timeout=120)
    db_item = {
        "status": "PENDING",
        "workspace_count": len(workspaces) if dc == 0 and isinstance(workspaces, list) else None,
        "workspaces": [],
        "workspace_access_probe": "NOT_PROVEN",
    }
    if dc == 0 and isinstance(workspaces, list):
        for ws in workspaces[:10]:
            item = {
                "name": ws.get("name"),
                "resourceGroup": ws.get("resourceGroup"),
                "workspaceUrl": ws.get("workspaceUrl"),
            }
            db_item["workspaces"].append(item)
        for ws in workspaces:
            url = ws.get("workspaceUrl")
            if not url:
                continue
            host = url if str(url).startswith("https://") else f"https://{url}"
            env = os.environ.copy()
            env["DATABRICKS_HOST"] = host
            env["DATABRICKS_AUTH_TYPE"] = "azure-cli"
            try:
                c, o, e = run(["databricks", "current-user", "me", "-o", "json"], timeout=60, env=env)
                if c == 0:
                    db_item["status"] = "PASS"
                    db_item["workspace_access_probe"] = "PASS"
                    db_item["proved_workspace"] = ws.get("name")
                    break
            except Exception as exc:
                db_item["probe_error"] = str(exc)
    result["checks"]["databricks"] = db_item
    print(f"DATABRICKS_WORKSPACE_ACCESS={db_item['workspace_access_probe']}")
    if db_item["workspace_access_probe"] != "PASS":
        result["blockers"].append("Databricks workspace access/minimum execution capability")

    # 6. GitHub OIDC: actual OIDC proof cannot be claimed from a local login alone.
    git_remote = None
    if shutil.which("git"):
        c, o, e = run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], timeout=15)
        if c == 0:
            git_remote = o
    github_status = "PENDING"
    github_detail = "No GitHub origin detected"
    if git_remote and "github.com" in git_remote.lower():
        github_detail = "GitHub origin exists; actual Azure OIDC workflow proof not yet executed"
    result["checks"]["github_oidc"] = {
        "status": github_status,
        "origin": git_remote,
        "detail": github_detail,
    }
    print(f"GITHUB_AZURE_OIDC={github_status}")
    result["blockers"].append("GitHub → Azure OIDC actual workflow proof")

    # 7. Host capabilities
    host = {}
    if HOST_RESULT.exists():
        try:
            host = json.loads(HOST_RESULT.read_text(encoding="utf-8-sig"))
        except Exception:
            host = {}

    pbi = host.get("power_bi_desktop", "PENDING")
    windows_skill = host.get("windows_skill_proof_toolchain", "PENDING")
    result["checks"]["power_bi_desktop_fallback"] = {
        "status": "PASS" if pbi == "PASS" else "PENDING",
        "host_detail": host,
    }
    result["checks"]["windows_skill_proof_toolchain"] = {
        "status": "PASS" if windows_skill == "PASS" else "PENDING",
        "host_detail": host,
    }
    print(f"POWER_BI_DESKTOP_FALLBACK={pbi}")
    print(f"WINDOWS_SKILL_PROOF_TOOLCHAIN={windows_skill}")
    if pbi != "PASS":
        result["blockers"].append("Power BI Desktop fallback capability")
    else:
        # Installation alone is not publish capability.
        result["blockers"].append("Power BI publish/API or Desktop publish actual capability")
    if windows_skill != "PASS":
        result["blockers"].append("Windows SSIS/SSAS build/run capability")

    # 8. Teams and AAS high-risk boundaries remain actual-capability requirements.
    result["checks"]["teams"] = {
        "status": "PENDING",
        "detail": "Agents Toolkit is installed, but tenant/custom-app deployment capability is not yet proven",
    }
    result["checks"]["azure_analysis_services"] = {
        "status": "PENDING",
        "detail": "Deploy/admin capability not yet proven",
    }
    print("TEAMS_DEPLOY_CAPABILITY=PENDING")
    print("AAS_DEPLOY_ADMIN_CAPABILITY=PENDING")
    result["blockers"].append("Teams tenant/custom-app deployment capability")
    result["blockers"].append("Azure Analysis Services deploy/admin capability")

    finalize(result)
    return 0

def finalize(result: dict[str, Any]) -> None:
    # Deduplicate blockers preserving order.
    seen = set()
    blockers = []
    for item in result.get("blockers", []):
        if item not in seen:
            seen.add(item)
            blockers.append(item)
    result["blockers"] = blockers
    result["zero_intervention_ready"] = "PASS" if not blockers else "PENDING_CAPABILITY"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = [
        "# TechScope Zero-Intervention Deep Readiness",
        "",
        f"- ZERO_INTERVENTION_READY: **{result['zero_intervention_ready']}**",
        f"- Cloud mutation performed: **{result.get('cloud_mutation_performed', False)}**",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        md.extend([f"- {x}" for x in blockers])
    else:
        md.append("- None")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    manual = [
        "# Manual Actions",
        "",
        "Only genuine external/human boundaries should remain here.",
        "",
    ]
    if blockers:
        manual.extend([f"- {x}" for x in blockers])
    else:
        manual.append("- None")
    MANUAL.write_text("\n".join(manual) + "\n", encoding="utf-8")

    print(f"ZERO_INTERVENTION_READY={result['zero_intervention_ready']}")
    print(f"BLOCKER_COUNT={len(blockers)}")
    print(f"READINESS_RESULT={OUT.relative_to(ROOT)}")
    print(f"MANUAL_ACTIONS={MANUAL.relative_to(ROOT)}")
    print("ZERO_INTERVENTION_DEEP_READINESS=PASS")

if __name__ == "__main__":
    raise SystemExit(main())
