#!/usr/bin/env python3
"""Read-only TechScope cloud readiness discovery.

No Azure resource creation/update/deletion is performed.
No access token, refresh token, key, secret, password, or credential string is
written to results.

This is a bootstrap/readiness artifact, not architecture source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "results" / "latest"
TARGET_PATH = ROOT / "config" / "cloud-target.dev.json"
READINESS_JSON = LATEST / "bootstrap-readiness.json"
READINESS_MD = LATEST / "bootstrap-readiness.md"
MANUAL = LATEST / "manual-actions.md"

def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env={**os.environ, "AZURE_CORE_ONLY_SHOW_ERRORS": "true"},
        )
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"

def az_json(args: list[str], timeout: int = 30) -> tuple[int, Any, str]:
    code, out, err = run(["az", *args, "-o", "json"], timeout=timeout)
    if code != 0:
        return code, None, err or out
    try:
        return 0, json.loads(out), ""
    except json.JSONDecodeError as exc:
        return 1, None, f"JSON decode error: {exc}"

def az_text(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    return run(["az", *args, "-o", "tsv"], timeout=timeout)

def result(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev")
    args = parser.parse_args()

    LATEST.mkdir(parents=True, exist_ok=True)
    target = json.loads(TARGET_PATH.read_text(encoding="utf-8-sig"))

    report: dict[str, Any] = {
        "timestamp": now(),
        "environment": args.env,
        "probe_mode": "READ_ONLY",
        "ENVIRONMENT_READY": "PASS",
        "ZERO_INTERVENTION_READY": "PENDING",
        "capabilities": {},
        "blockers": [],
        "notes": [
            "No cloud resource mutation performed.",
            "No secret/token material persisted.",
            "This is a derived bootstrap-readiness artifact, not Architecture Source of Truth.",
        ],
    }

    # 1) Authentication and subscription.
    code, account, err = az_json(["account", "show"], timeout=20)
    if code != 0 or not isinstance(account, dict):
        report["capabilities"]["azure_auth"] = result("USER_ACTION_REQUIRED", "Azure CLI is not authenticated.")
        report["blockers"].append("AZURE_INTERACTIVE_LOGIN")
        report["ZERO_INTERVENTION_READY"] = "USER_ACTION_REQUIRED"

        write_json(READINESS_JSON, report)
        write_text(
            MANUAL,
            "# Manual Actions\n\n"
            "blocked_step: cloud-readiness\n"
            "reason: Azure CLI in the TechScope Dev Container is not authenticated.\n"
            "where_to_fix: Windows PowerShell at C:\\TechScope\n"
            "exact_manual_action: docker exec -it techscope-dev az login --use-device-code\n"
            "how_to_verify: docker exec techscope-dev az account show -o table\n"
            "resume_command: .\\RUN_P0_FOUNDATION_CLOUD_READINESS.cmd\n"
        )
        write_text(
            READINESS_MD,
            "# TechScope Bootstrap Readiness\n\n"
            f"timestamp: {report['timestamp']}\n\n"
            "ENVIRONMENT_READY: PASS\n\n"
            "ZERO_INTERVENTION_READY: USER_ACTION_REQUIRED\n\n"
            "Blocker: Azure interactive login is required once.\n"
        )
        print("FOUNDATION_CLOUD_READINESS_PROBE=PASS")
        print("AZURE_AUTH=USER_ACTION_REQUIRED")
        print("ZERO_INTERVENTION_READY=USER_ACTION_REQUIRED")
        print("MANUAL_ACTIONS=results/latest/manual-actions.md")
        return 0

    subscription_id = str(account.get("id", ""))
    tenant_id = str(account.get("tenantId", ""))
    subscription_name = str(account.get("name", ""))
    user = account.get("user") if isinstance(account.get("user"), dict) else {}
    report["target"] = {
        "subscription_id": subscription_id,
        "subscription_name": subscription_name,
        "tenant_id": tenant_id,
        "identity_type": user.get("type"),
        "identity_name": user.get("name"),
    }
    report["capabilities"]["azure_auth"] = result("PASS", "az account show succeeded.")

    # Prove a management token can be acquired without persisting it.
    code, expiry, err = az_text(
        ["account", "get-access-token", "--resource", "https://management.azure.com/", "--query", "expiresOn"],
        timeout=20,
    )
    report["capabilities"]["azure_management_token"] = (
        result("PASS", "Management-plane access token acquisition succeeded; token value was not persisted.", expires_on=expiry)
        if code == 0
        else result("FAIL", err)
    )
    if code != 0:
        report["blockers"].append("AZURE_MANAGEMENT_TOKEN")

    # 2) Resource provider state.
    provider_states: dict[str, str] = {}
    for namespace in target["required_resource_providers"]:
        code, state, err = az_text(
            ["provider", "show", "--namespace", namespace, "--query", "registrationState"],
            timeout=20,
        )
        provider_states[namespace] = state if code == 0 else f"ERROR:{err[:160]}"

    unregistered = sorted(
        ns for ns, state in provider_states.items() if state.lower() != "registered"
    )
    report["capabilities"]["resource_providers"] = result(
        "PASS" if not unregistered else "PENDING",
        "Required provider registration states queried.",
        states=provider_states,
        unregistered=unregistered,
    )
    if unregistered:
        report["blockers"].append("RESOURCE_PROVIDER_REGISTRATION")

    # 3) Candidate region/model/quota discovery, no resource creation.
    chosen: dict[str, Any] | None = None
    discovery: list[dict[str, Any]] = []
    for location in target["location_preferences"]:
        m_code, models, m_err = az_json(["cognitiveservices", "model", "list", "--location", location], timeout=45)
        u_code, usages, u_err = az_json(["cognitiveservices", "usage", "list", "--location", location], timeout=45)

        model_names: set[str] = set()
        if m_code == 0 and isinstance(models, list):
            for item in models:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if isinstance(name, str):
                    model_names.add(name)
                model_obj = item.get("model")
                if isinstance(model_obj, dict) and isinstance(model_obj.get("name"), str):
                    model_names.add(model_obj["name"])

        generations = [x for x in target["generation_model_candidates"] if x in model_names]
        embeddings = [x for x in target["embedding_model_candidates"] if x in model_names]

        positive_quota = False
        if u_code == 0 and isinstance(usages, list):
            for item in usages:
                if not isinstance(item, dict):
                    continue
                limit = item.get("limit")
                try:
                    if limit is not None and float(limit) > 0:
                        positive_quota = True
                        break
                except (TypeError, ValueError):
                    pass

        entry = {
            "location": location,
            "model_query": "PASS" if m_code == 0 else "FAIL",
            "usage_query": "PASS" if u_code == 0 else "FAIL",
            "generation_candidates_found": generations,
            "embedding_candidates_found": embeddings,
            "positive_quota_observed": positive_quota,
            "model_error": m_err[:240] if m_err else "",
            "usage_error": u_err[:240] if u_err else "",
        }
        discovery.append(entry)

        if chosen is None and generations and embeddings and u_code == 0 and positive_quota:
            chosen = {
                "location": location,
                "generation_model": generations[0],
                "embedding_model": embeddings[0],
            }

    report["capabilities"]["azure_openai_discovery"] = result(
        "PASS" if chosen else "PENDING",
        "Subscription/region model and quota discovery completed. This does not substitute for post-deployment minimum API evidence.",
        selected_candidate=chosen,
        regions=discovery,
    )
    if chosen is None:
        report["blockers"].append("AZURE_OPENAI_MODEL_OR_QUOTA")

    # 4) ARM provider-level validation: checks deployability without creating resources.
    validate_location = (chosen or {}).get("location") or target["location_preferences"][0]
    validation_rg = "rg-techscope-readiness-validation"
    code, out, err = run(
        [
            "az", "deployment", "sub", "validate",
            "--validation-level", "Provider",
            "--location", validate_location,
            "--template-file", "infra/bicep/readiness.bicep",
            "--parameters",
            f"location={validate_location}",
            f"validationResourceGroupName={validation_rg}",
            "-o", "json",
        ],
        timeout=60,
    )
    report["capabilities"]["arm_provider_validation"] = (
        result("PASS", "Subscription-scope Provider validation succeeded; no template deployment was executed.")
        if code == 0
        else result("FAIL", (err or out)[:1000])
    )
    if code != 0:
        report["blockers"].append("AZURE_DEPLOY_PERMISSION")

    # 5) High-risk boundaries that cannot be honestly proven before target artifacts exist.
    report["capabilities"]["github_azure_oidc"] = result(
        "PENDING_RUNTIME_PROOF",
        "Pinned OIDC workflow skeleton exists; actual GitHub-to-Azure federated login must succeed before Zero-Intervention PASS.",
    )
    report["capabilities"]["databricks_workspace"] = result(
        "PENDING_TARGET",
        "Databricks CLI is installed, but target workspace/service-principal capability requires an existing/reused workspace or provision stage.",
    )
    report["capabilities"]["power_bi_fabric"] = result(
        "PENDING_EXTERNAL",
        "Power BI/Fabric license/workspace/API or Desktop fallback capability is not proven by this container probe.",
    )
    report["capabilities"]["teams_tenant"] = result(
        "PENDING_EXTERNAL",
        "Teams tenant/custom-app/admin-consent capability is deferred until final deployment boundary.",
    )
    report["capabilities"]["analysis_services"] = result(
        "PENDING_TARGET",
        "AAS deploy/admin capability requires target service/identity context.",
    )
    report["capabilities"]["windows_skill_proof"] = result(
        "PENDING_WINDOWS_LANE",
        "SSIS/SSAS Windows capability is verified by the separate Windows lane, not the MAIN container.",
    )

    pending_external = [
        "GITHUB_AZURE_OIDC_RUNTIME",
        "DATABRICKS_TARGET_CAPABILITY",
        "POWER_BI_FABRIC_CAPABILITY",
        "TEAMS_TENANT_CAPABILITY",
        "AAS_CAPABILITY",
        "WINDOWS_SKILL_PROOF_CAPABILITY",
        "AZURE_OPENAI_MINIMUM_API_POST_DEPLOY",
    ]
    report["blockers"].extend(pending_external)
    report["ZERO_INTERVENTION_READY"] = "PENDING_CAPABILITY"

    write_json(READINESS_JSON, report)

    md = [
        "# TechScope Bootstrap Readiness",
        "",
        f"timestamp: {report['timestamp']}",
        "",
        "ENVIRONMENT_READY: PASS",
        f"ZERO_INTERVENTION_READY: {report['ZERO_INTERVENTION_READY']}",
        "",
        "## Azure target",
        f"- subscription: {subscription_name} ({subscription_id})",
        f"- tenant: {tenant_id}",
        f"- selected AI candidate: {chosen}",
        "",
        "## Remaining high-risk capability boundaries",
    ]
    md.extend(f"- {x}" for x in report["blockers"])
    md += [
        "",
        "This report is a derived bootstrap artifact, not architecture source of truth.",
    ]
    write_text(READINESS_MD, "\n".join(md) + "\n")

    write_text(
        MANUAL,
        "# Manual Actions\n\n"
        "No immediate manual action is required for local Foundation work.\n\n"
        "ZERO_INTERVENTION_READY remains PENDING_CAPABILITY until the external/cloud target capabilities in bootstrap-readiness.json are actually proven.\n"
    )

    print("FOUNDATION_CLOUD_READINESS_PROBE=PASS")
    print("AZURE_AUTH=PASS")
    print(f"AZURE_SUBSCRIPTION={subscription_name}")
    print(f"AZURE_OPENAI_CANDIDATE={'PASS' if chosen else 'PENDING'}")
    print(f"ARM_PROVIDER_VALIDATION={'PASS' if code == 0 else 'FAIL'}")
    print("ZERO_INTERVENTION_READY=PENDING_CAPABILITY")
    print("READINESS=results/latest/bootstrap-readiness.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
