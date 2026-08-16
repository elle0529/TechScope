#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cloud-target.dev.json"
OUT = ROOT / "results" / "latest" / "provider-remediation-r1.json"

def az(args: list[str], timeout: int = 900):
    cp = subprocess.run(
        ["az", *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()

def state(namespace: str) -> str:
    c, out, err = az(
        ["provider", "show", "--namespace", namespace,
         "--query", "registrationState", "-o", "tsv"],
        timeout=60,
    )
    return out.strip() if c == 0 else "UNKNOWN"

def register(namespace: str) -> dict:
    before = state(namespace)
    if before == "Registered":
        return {
            "namespace": namespace,
            "before": before,
            "action": "REUSE",
            "register_exit": 0,
            "after": before,
        }

    c, out, err = az(
        ["provider", "register", "--namespace", namespace,
         "--wait", "--only-show-errors", "-o", "none"],
        timeout=900,
    )
    after = state(namespace)
    return {
        "namespace": namespace,
        "before": before,
        "action": "REGISTER",
        "register_exit": c,
        "after": after,
        "error": None if c == 0 else (err or out)[:1000],
    }

def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    providers = (
        cfg.get("required_resource_providers")
        or cfg.get("required_providers")
        or []
    )
    if not providers:
        print("PROVIDER_REMEDIATION=FAIL CONFIG_PROVIDER_COUNT=0")
        return 2

    print(f"PROVIDER_REMEDIATION=START EXPECTED={len(providers)}")
    before = {ns: state(ns) for ns in providers}
    missing = [ns for ns in providers if before[ns] != "Registered"]
    print(f"PROVIDER_BEFORE_REGISTERED={len(providers)-len(missing)}/{len(providers)}")
    print(f"PROVIDER_TO_REGISTER={len(missing)}")

    rows = []
    if missing:
        # Provider registrations are subscription-level independent operations.
        # Keep concurrency conservative.
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(missing))) as ex:
            futures = {ex.submit(register, ns): ns for ns in missing}
            for fut in concurrent.futures.as_completed(futures):
                row = fut.result()
                rows.append(row)
                print(
                    f"PROVIDER={row['namespace']} "
                    f"ACTION={row['action']} AFTER={row['after']} "
                    f"EXIT={row['register_exit']}"
                )

    rows.extend(
        {
            "namespace": ns,
            "before": "Registered",
            "action": "REUSE",
            "register_exit": 0,
            "after": "Registered",
        }
        for ns in providers
        if ns not in missing
    )
    rows.sort(key=lambda x: providers.index(x["namespace"]))

    registered = sum(1 for x in rows if x["after"] == "Registered")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "expected": len(providers),
                "registered": registered,
                "items": rows,
                "cloud_resource_created": False,
                "subscription_configuration_mutated": bool(missing),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"PROVIDER_AFTER_REGISTERED={registered}/{len(providers)}")
    print(f"PROVIDER_RESULT={OUT.relative_to(ROOT)}")
    if registered == len(providers):
        print("PROVIDER_REMEDIATION=PASS")
    else:
        print("PROVIDER_REMEDIATION=PENDING")
    # Do not abort host installation if one provider remains registering.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
