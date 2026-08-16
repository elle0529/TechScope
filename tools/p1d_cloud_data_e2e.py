#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cloud-target.dev.json"
BICEP = ROOT / "infra" / "bicep" / "p1-data.bicep"
NOTEBOOK = ROOT / "databricks" / "src" / "02_cloud_data_e2e.py"
STATE = ROOT / "results" / "latest" / "p1d-state.json"
SUMMARY = ROOT / "results" / "latest" / "p1d-summary.json"
COMPONENTS = ROOT / "results" / "latest" / "p1d-component-results.json"
RUNTIME = ROOT / "generated" / "runtime-config.json"

P1A_FILES = [
    "technology.csv",
    "category.csv",
    "relation.csv",
    "company_usecase.csv",
    "architecture_mapping.csv",
]

REQUIRED_PROVIDERS = [
    "Microsoft.Resources",
    "Microsoft.Storage",
    "Microsoft.DataFactory",
    "Microsoft.Databricks",
    "Microsoft.Sql",
]

def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def run(
    args: list[str],
    *,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    check: bool = False,
    secret: bool = False,
) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    if check and cp.returncode != 0:
        label = args[0] if secret else " ".join(args[:4])
        raise RuntimeError(
            f"Command failed ({label}) exit={cp.returncode}: "
            f"{(cp.stderr or cp.stdout).strip()[:2000]}"
        )
    return cp

def run_with_heartbeat(
    args: list[str],
    *,
    timeout: int,
    heartbeat_label: str,
    heartbeat_seconds: int = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as out_f, \
         tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as err_f:
        proc = subprocess.Popen(
            args,
            text=True,
            stdout=out_f,
            stderr=err_f,
            env=env,
        )
        last_heartbeat = -heartbeat_seconds
        while proc.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed - last_heartbeat >= heartbeat_seconds:
                print(
                    f"{heartbeat_label}=RUNNING ELAPSED_SECONDS={int(elapsed)}",
                    flush=True,
                )
                last_heartbeat = elapsed
            if elapsed > timeout:
                proc.kill()
                proc.wait()
                raise TimeoutError(
                    f"{heartbeat_label} exceeded timeout={timeout}s"
                )
            time.sleep(2)

        out_f.flush()
        err_f.flush()
        out_f.seek(0)
        err_f.seek(0)
        return subprocess.CompletedProcess(
            args=args,
            returncode=proc.returncode,
            stdout=out_f.read(),
            stderr=err_f.read(),
        )


def az_json(args: list[str], timeout: int = 300) -> Any:
    cp = run(["az", *args, "-o", "json"], timeout=timeout, check=True)
    return json.loads(cp.stdout or "null")

def dbx_json(args: list[str], env: dict[str, str], timeout: int = 300) -> Any:
    cp = run(["databricks", *args, "-o", "json"], env=env, timeout=timeout, check=True)
    return json.loads(cp.stdout or "null")

def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def checkpoint(stage: str, status: str, detail: str = "") -> None:
    data = load_json(STATE, {"started_at": now(), "stages": {}})
    data["updated_at"] = now()
    data["stages"][stage] = {"status": status, "detail": detail, "timestamp": now()}
    write_json(STATE, data)
    print(f"STAGE={stage} STATUS={status}" + (f" DETAIL={detail}" if detail else ""))

def provider_state(namespace: str) -> str:
    cp = run(
        ["az", "provider", "show", "--namespace", namespace,
         "--query", "registrationState", "-o", "tsv"],
        timeout=60,
    )
    return cp.stdout.strip() if cp.returncode == 0 else "UNKNOWN"

def random_sql_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%_-"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(28))
        if (
            any(c.isupper() for c in value)
            and any(c.islower() for c in value)
            and any(c.isdigit() for c in value)
            and any(c in "!@#%_-" for c in value)
        ):
            return value

def deployment_params(path: Path, location: str, suffix: str, user: str, password: str) -> None:
    payload = {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "location": {"value": location},
            "project": {"value": "techscope"},
            "env": {"value": "dev"},
            "suffix": {"value": suffix},
            "sqlAdminLogin": {"value": user},
            "sqlAdminPassword": {"value": password},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)

def flatten_outputs(deployment: dict[str, Any]) -> dict[str, Any]:
    outputs = (((deployment or {}).get("properties") or {}).get("outputs") or {})
    return {key: value.get("value") for key, value in outputs.items()}

def stage_gate(cfg: dict[str, Any], suffix: str, sql_user: str, sql_password: str) -> str:
    checkpoint("stage-gate", "START")
    account = az_json(["account", "show"], timeout=60)
    print(f"AZURE_AUTH=PASS SUBSCRIPTION={account.get('name')}")

    bad = []
    for ns in REQUIRED_PROVIDERS:
        st = provider_state(ns)
        print(f"PROVIDER={ns} STATE={st}")
        if st != "Registered":
            bad.append(ns)
    if bad:
        checkpoint("stage-gate", "FAIL", "Unregistered: " + ", ".join(bad))
        raise RuntimeError("P1D required resource providers are not Registered.")

    locations = cfg.get("location_preferences") or ["koreacentral", "eastus2", "swedencentral"]

    cp = run(
        [
            "az", "bicep", "build",
            "--file", str(BICEP),
            "--outfile", "/tmp/techscope-p1d-build.json",
        ],
        timeout=120,
    )
    if cp.returncode != 0:
        diagnostic = (cp.stderr or cp.stdout).strip()
        print("BICEP_BUILD_DIAGNOSTIC_START")
        print(diagnostic)
        print("BICEP_BUILD_DIAGNOSTIC_END")
        checkpoint("stage-gate", "FAIL", "Bicep build")
        raise RuntimeError(diagnostic[:5000])
    print("BICEP_BUILD=PASS")

    selected = None
    with tempfile.TemporaryDirectory() as td:
        param_file = Path(td) / "params.json"
        for location in locations:
            deployment_params(param_file, location, suffix, sql_user, sql_password)
            print(f"P1D_PROVIDER_VALIDATION={location}")
            cp = run(
                [
                    "az", "deployment", "sub", "validate",
                    "--location", location,
                    "--template-file", str(BICEP),
                    "--parameters", f"@{param_file}",
                    "--validation-level", "Provider",
                    "--only-show-errors",
                    "-o", "none",
                ],
                timeout=240,
            )
            if cp.returncode == 0:
                selected = location
                break
            print(f"P1D_PROVIDER_VALIDATION_FAIL={location}")

    if not selected:
        checkpoint("stage-gate", "FAIL", "No location passed Provider validation")
        raise RuntimeError("No preferred region passed P1D Provider validation.")

    checkpoint("stage-gate", "PASS", selected)
    print(f"P1D_STAGE_GATE=PASS LOCATION={selected}")
    return selected

def ensure_datafactory_extension() -> None:
    cp = run(["az", "extension", "show", "--name", "datafactory", "-o", "none"], timeout=30)
    if cp.returncode != 0:
        print("AZ_DATAFACTORY_EXTENSION=INSTALL")
        run(
            ["az", "extension", "add", "--name", "datafactory", "--only-show-errors"],
            timeout=180,
            check=True,
        )
    print("AZ_DATAFACTORY_EXTENSION=PASS")

def provision(location: str, suffix: str, sql_user: str, sql_password: str) -> dict[str, Any]:
    checkpoint("provision", "START")
    deployment_name = f"techscope-p1d-{suffix}"
    with tempfile.TemporaryDirectory() as td:
        params = Path(td) / "params.json"
        deployment_params(params, location, suffix, sql_user, sql_password)
        cp = run_with_heartbeat(
            [
                "az", "deployment", "sub", "create",
                "--name", deployment_name,
                "--location", location,
                "--template-file", str(BICEP),
                "--parameters", f"@{params}",
                "--only-show-errors",
                "-o", "json",
            ],
            timeout=1800,
            heartbeat_label="P1D_PROVISION",
            heartbeat_seconds=30,
        )
        if cp.returncode != 0:
            checkpoint("provision", "FAIL", (cp.stderr or cp.stdout)[:500])
            raise RuntimeError((cp.stderr or cp.stdout)[:3000])
        deployment = json.loads(cp.stdout)

    outputs = flatten_outputs(deployment)
    runtime = {
        "state": "P1_DATA_PROVISIONED",
        "timestamp": now(),
        "location": outputs["location"],
        "resource_group": outputs["resourceGroupName"],
        "storage_account": outputs["storageAccountName"],
        "storage_dfs_endpoint": outputs["storageDfsEndpoint"],
        "file_system": outputs["fileSystemName"],
        "data_factory": outputs["dataFactoryName"],
        "databricks_workspace": outputs["databricksWorkspaceName"],
        "databricks_workspace_url": outputs["databricksWorkspaceUrl"],
        "databricks_workspace_resource_id": outputs["databricksWorkspaceResourceId"],
        "sql_server": outputs["sqlServerName"],
        "sql_server_fqdn": outputs["sqlServerFqdn"],
        "sql_database": outputs["sqlDatabaseName"],
        "sql_admin_login": sql_user,
        "secrets_persisted": False,
    }
    write_json(RUNTIME, runtime)

    ev = ROOT / "evidence" / "adls" / "p1d-deployment.json"
    write_json(ev, {
        "component": "CMP_ADLS",
        "status": "PASS",
        "deployment_name": deployment_name,
        "resource_group": outputs["resourceGroupName"],
        "storage_account": outputs["storageAccountName"],
        "file_system": outputs["fileSystemName"],
        "location": outputs["location"],
        "timestamp": now(),
        "secret_material": "NOT_STORED",
    })
    checkpoint("provision", "PASS", outputs["resourceGroupName"])
    return runtime

def storage_env(runtime: dict[str, Any]) -> tuple[dict[str, str], str]:
    keys = az_json(
        [
            "storage", "account", "keys", "list",
            "--resource-group", runtime["resource_group"],
            "--account-name", runtime["storage_account"],
        ],
        timeout=60,
    )
    if not keys:
        raise RuntimeError("Storage account keys query returned empty.")
    key = keys[0]["value"]
    env = os.environ.copy()
    env["AZURE_STORAGE_ACCOUNT"] = runtime["storage_account"]
    env["AZURE_STORAGE_KEY"] = key
    return env, key

def upload_structured(runtime: dict[str, Any]) -> str:
    checkpoint("seed-adls", "START")
    env, key = storage_env(runtime)
    fs = runtime["file_system"]
    account = runtime["storage_account"]

    for directory in ["raw/SRC001", "landing/structured"]:
        run(
            [
                "az", "storage", "fs", "directory", "create",
                "-f", fs, "-n", directory,
                "--account-name", account,
                "--only-show-errors", "-o", "none",
            ],
            env=env, timeout=90, check=True, secret=True,
        )

    raw = ROOT / "source" / "rawdata.md"
    if not raw.exists():
        raise RuntimeError("source/rawdata.md missing")

    uploads = [(raw, "raw/SRC001/rawdata.md")]
    for name in P1A_FILES:
        source = ROOT / "extractor" / "output" / name
        if not source.exists():
            raise RuntimeError(f"P1A output missing: {source}")
        uploads.append((source, f"landing/structured/{name}"))

    for source, target in uploads:
        run(
            [
                "az", "storage", "fs", "file", "upload",
                "-f", fs,
                "--account-name", account,
                "--source", str(source),
                "--path", target,
                "--overwrite", "true",
                "--only-show-errors", "-o", "none",
            ],
            env=env, timeout=120, check=True, secret=True,
        )
        print(f"ADLS_UPLOAD=PASS PATH={target}")

    listed = az_json_with_env(
        [
            "storage", "fs", "file", "list",
            "-f", fs,
            "--account-name", account,
            "--path", "landing/structured",
            "--recursive", "true",
            "--exclude-dir",
        ],
        env=env,
        timeout=120,
    )
    names = sorted(x.get("name") for x in listed if isinstance(x, dict) and x.get("name"))
    write_json(ROOT / "evidence" / "adls" / "p1d-output.json", {
        "component": "CMP_ADLS",
        "status": "PASS",
        "verified_paths": names,
        "timestamp": now(),
    })
    checkpoint("seed-adls", "PASS", f"{len(names)} files")
    return key

def az_json_with_env(args: list[str], env: dict[str, str], timeout: int = 300) -> Any:
    cp = run(["az", *args, "-o", "json"], timeout=timeout, env=env, check=True, secret=True)
    return json.loads(cp.stdout or "null")

def wait_adf_run(runtime: dict[str, Any], run_id: str) -> dict[str, Any]:
    for _ in range(90):
        data = az_json(
            [
                "datafactory", "pipeline-run", "show",
                "--resource-group", runtime["resource_group"],
                "--factory-name", runtime["data_factory"],
                "--run-id", run_id,
            ],
            timeout=60,
        )
        status = data.get("status")
        if status in {"Succeeded", "Failed", "Cancelled"}:
            return data
        time.sleep(10)
    raise TimeoutError("ADF pipeline run exceeded 15 minutes.")

def run_adf(runtime: dict[str, Any]) -> bool:
    checkpoint("run-adf", "START")
    ensure_datafactory_extension()

    final = None
    for attempt in range(1, 4):
        print(f"ADF_RUN_ATTEMPT={attempt}")
        cp = run(
            [
                "az", "datafactory", "pipeline", "create-run",
                "--resource-group", runtime["resource_group"],
                "--factory-name", runtime["data_factory"],
                "--name", "PL_Ingest_TechScope",
                "--parameters", '{"structured_folder":"landing/structured"}',
                "--only-show-errors",
                "-o", "json",
            ],
            timeout=90,
        )
        if cp.returncode != 0:
            final = {"status": "CreateRunFailed", "error": (cp.stderr or cp.stdout)[:1000]}
        else:
            run_id = json.loads(cp.stdout)["runId"]
            final = wait_adf_run(runtime, run_id)
            final["runId"] = run_id
            if final.get("status") == "Succeeded":
                break
        if attempt < 3:
            print("ADF_RBAC_PROPAGATION_WAIT=30s")
            time.sleep(30)

    ev_exec = {
        "component": "CMP_ADF",
        "status": "PASS" if final and final.get("status") == "Succeeded" else "FAIL",
        "pipeline": "PL_Ingest_TechScope",
        "factory": runtime["data_factory"],
        "run": final,
        "timestamp": now(),
    }
    write_json(ROOT / "evidence" / "adf" / "p1d-execution.json", ev_exec)

    if ev_exec["status"] != "PASS":
        checkpoint("run-adf", "FAIL", str(final.get("status") if final else "unknown"))
        return False

    env, _ = storage_env(runtime)
    bronze = az_json_with_env(
        [
            "storage", "fs", "file", "list",
            "-f", runtime["file_system"],
            "--account-name", runtime["storage_account"],
            "--path", "bronze",
            "--recursive", "true",
            "--exclude-dir",
        ],
        env=env,
        timeout=120,
    )
    paths = sorted(x.get("name") for x in bronze if isinstance(x, dict) and x.get("name"))
    expected = {f"bronze/{name.replace('.csv','')}" for name in P1A_FILES}
    prefixes = {"/".join(x.split("/")[:2]) for x in paths}
    good = expected.issubset(prefixes)
    write_json(ROOT / "evidence" / "adf" / "p1d-output.json", {
        "component": "CMP_ADF",
        "status": "PASS" if good else "FAIL",
        "bronze_paths": paths[:100],
        "expected_entity_prefixes": sorted(expected),
        "timestamp": now(),
    })
    checkpoint("run-adf", "PASS" if good else "FAIL", f"bronze files={len(paths)}")
    return good

def databricks_env(runtime: dict[str, Any]) -> dict[str, str]:
    host = runtime["databricks_workspace_url"]
    if not str(host).startswith("https://"):
        host = "https://" + str(host)
    env = os.environ.copy()
    env["DATABRICKS_HOST"] = host
    env["DATABRICKS_AUTH_TYPE"] = "azure-cli"
    return env

def wait_databricks_access(env: dict[str, str]) -> dict[str, Any] | None:
    for attempt in range(1, 11):
        cp = run(["databricks", "current-user", "me", "-o", "json"], env=env, timeout=60)
        if cp.returncode == 0:
            try:
                return json.loads(cp.stdout)
            except Exception:
                pass
        print(f"DATABRICKS_ACCESS_WAIT={attempt}/10")
        time.sleep(30)
    return None

def put_secret(env: dict[str, str], scope: str, key: str, value: str) -> None:
    cp = run(
        [
            "databricks", "secrets", "put-secret",
            scope, key,
            "--string-value", value,
        ],
        env=env,
        timeout=60,
        secret=True,
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout)[:1000])

def select_spark(env: dict[str, str]) -> tuple[str, str]:
    versions = dbx_json(["clusters", "spark-versions"], env, timeout=60)
    vrows = versions.get("versions", versions if isinstance(versions, list) else [])
    if not vrows:
        raise RuntimeError("No Databricks Spark versions returned.")

    def version_tuple(row: dict[str, Any]) -> tuple[int, int, int]:
        key = str(row.get("key", ""))
        match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", key)
        if not match:
            return (0, 0, 0)
        return tuple(int(x or 0) for x in match.groups())

    def is_x64_standard_runtime(row: dict[str, Any]) -> bool:
        key = str(row.get("key", "")).lower()
        name = str(row.get("name", "")).lower()
        arch_markers = ("aarch64", "arm64", " arm ", "(arm")
        return (
            "ml" not in name
            and "gpu" not in name
            and not any(marker in key for marker in arch_markers)
            and not any(marker in name for marker in arch_markers)
        )

    preferred = [
        x for x in vrows
        if "lts" in str(x.get("name", "")).lower()
        and is_x64_standard_runtime(x)
    ]
    candidates = preferred or [
        x for x in vrows
        if is_x64_standard_runtime(x)
    ]
    if not candidates:
        raise RuntimeError("No x64-compatible non-ML Databricks runtime returned by workspace.")

    candidates.sort(key=version_tuple, reverse=True)
    spark_version = candidates[0]["key"]
    print(
        "DATABRICKS_RUNTIME_CANDIDATES_X64="
        + ",".join(str(x.get("key")) for x in candidates[:8]),
        flush=True,
    )

    selected_key = str(spark_version).lower()
    if "aarch64" in selected_key or "arm64" in selected_key:
        raise RuntimeError(
            f"Runtime selector regression: ARM runtime selected for x64 node: {spark_version}"
        )

    nodes = dbx_json(["clusters", "list-node-types"], env, timeout=60)
    nrows = nodes.get("node_types", nodes if isinstance(nodes, list) else [])
    if not nrows:
        raise RuntimeError("No Databricks node types returned.")

    by_id = {x.get("node_type_id"): x for x in nrows if x.get("node_type_id")}
    preferred_ids = [
        "Standard_D4as_v5",
        "Standard_D4s_v5",
        "Standard_D4ds_v5",
        "Standard_DS3_v2",
    ]
    node = next((x for x in preferred_ids if x in by_id), None)
    if node is None:
        filtered = [
            x for x in nrows
            if str(x.get("node_type_id", "")).startswith("Standard_D")
            and all(gpu not in str(x.get("node_type_id", "")) for gpu in ["NC", "ND", "NV"])
        ]
        if not filtered:
            filtered = nrows
        filtered.sort(key=lambda x: (x.get("num_cores", 999), x.get("memory_mb", 999999)))
        node = filtered[0]["node_type_id"]

    return spark_version, node

def run_databricks(runtime: dict[str, Any], storage_key: str, sql_user: str, sql_password: str) -> bool:
    checkpoint("run-databricks", "START")
    env = databricks_env(runtime)
    current_user = wait_databricks_access(env)
    if not current_user:
        write_json(ROOT / "evidence" / "databricks" / "p1d-execution.json", {
            "component": "CMP_DATABRICKS",
            "status": "FAIL",
            "detail": "Workspace access not proven after provisioning",
            "timestamp": now(),
        })
        checkpoint("run-databricks", "FAIL", "workspace access")
        return False

    print(f"DATABRICKS_WORKSPACE_ACCESS=PASS USER={current_user.get('userName') or current_user.get('displayName')}")

    scope = "techscope"
    cp = run(["databricks", "secrets", "create-scope", scope], env=env, timeout=60)
    if cp.returncode != 0 and "already exists" not in (cp.stderr + cp.stdout).lower():
        raise RuntimeError((cp.stderr or cp.stdout)[:1000])

    put_secret(env, scope, "adls-key", storage_key)
    put_secret(env, scope, "sql-user", sql_user)
    put_secret(env, scope, "sql-password", sql_password)
    print("DATABRICKS_SECRET_SCOPE=PASS")

    workspace_dir = "/Shared/TechScope"
    notebook_path = f"{workspace_dir}/02_cloud_data_e2e"
    run(["databricks", "workspace", "mkdirs", workspace_dir], env=env, timeout=60, check=True)
    run(
        [
            "databricks", "workspace", "import", notebook_path,
            "--file", str(NOTEBOOK),
            "--format", "SOURCE",
            "--language", "PYTHON",
            "--overwrite",
        ],
        env=env, timeout=120, check=True,
    )
    print("DATABRICKS_NOTEBOOK_IMPORT=PASS")

    spark_version, node_type = select_spark(env)
    print(f"DATABRICKS_SPARK_VERSION={spark_version}")
    print(f"DATABRICKS_NODE_TYPE={node_type}")

    job = {
        "run_name": "techscope-p1d-cloud-data-e2e",
        "timeout_seconds": 2400,
        "tasks": [
            {
                "task_key": "build_techscope",
                "new_cluster": {
                    "spark_version": spark_version,
                    "node_type_id": node_type,
                    "num_workers": 0,
                    "spark_conf": {
                        "spark.databricks.cluster.profile": "singleNode",
                        "spark.master": "local[*]",
                    },
                    "custom_tags": {
                        "ResourceClass": "SingleNode",
                        "Project": "TechScope",
                    },
                },
                "notebook_task": {
                    "notebook_path": notebook_path,
                    "base_parameters": {
                        "storage_account": runtime["storage_account"],
                        "file_system": runtime["file_system"],
                        "secret_scope": scope,
                        "adls_key_secret": "adls-key",
                        "sql_server_fqdn": runtime["sql_server_fqdn"],
                        "sql_database": runtime["sql_database"],
                        "sql_user_secret": "sql-user",
                        "sql_password_secret": "sql-password",
                    },
                },
                "timeout_seconds": 2100,
            }
        ],
    }

    with tempfile.TemporaryDirectory() as td:
        job_file = Path(td) / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        cp = run_with_heartbeat(
            [
                "databricks", "jobs", "submit",
                "--json", f"@{job_file}",
                "--timeout", "40m",
                "-o", "json",
            ],
            env=env,
            timeout=2600,
            heartbeat_label="DATABRICKS_JOB",
            heartbeat_seconds=30,
        )

    success = cp.returncode == 0
    payload = {}
    if cp.stdout.strip():
        try:
            payload = json.loads(cp.stdout)
        except Exception:
            payload = {"stdout": cp.stdout[-2000:]}
    if not success:
        payload["error"] = (cp.stderr or cp.stdout)[-3000:]

    write_json(ROOT / "evidence" / "databricks" / "p1d-execution.json", {
        "component": "CMP_DATABRICKS",
        "status": "PASS" if success else "FAIL",
        "workspace": runtime["databricks_workspace"],
        "spark_version": spark_version,
        "node_type_id": node_type,
        "job_result": payload,
        "timestamp": now(),
        "secret_values": "NOT_STORED",
    })
    if not success:
        checkpoint("run-databricks", "FAIL", "job submit/run")
        return False

    env_storage, _ = storage_env(runtime)
    gold_files = az_json_with_env(
        [
            "storage", "fs", "file", "list",
            "-f", runtime["file_system"],
            "--account-name", runtime["storage_account"],
            "--path", "gold",
            "--recursive", "true",
            "--exclude-dir",
        ],
        env=env_storage, timeout=120,
    )
    rag_files = az_json_with_env(
        [
            "storage", "fs", "file", "list",
            "-f", runtime["file_system"],
            "--account-name", runtime["storage_account"],
            "--path", "rag",
            "--recursive", "true",
            "--exclude-dir",
        ],
        env=env_storage, timeout=120,
    )
    gold_names = [x.get("name") for x in gold_files if isinstance(x, dict) and x.get("name")]
    rag_names = [x.get("name") for x in rag_files if isinstance(x, dict) and x.get("name")]
    output_pass = bool(gold_names) and any("knowledge_chunks.jsonl" in x for x in rag_names)

    write_json(ROOT / "evidence" / "databricks" / "p1d-output.json", {
        "component": "CMP_DATABRICKS",
        "status": "PASS" if output_pass else "FAIL",
        "gold_file_count": len(gold_names),
        "gold_sample": gold_names[:30],
        "rag_files": rag_names[:30],
        "timestamp": now(),
    })
    checkpoint("run-databricks", "PASS" if output_pass else "FAIL", f"gold={len(gold_names)}")
    return output_pass

def verify_sql(runtime: dict[str, Any], sql_user: str, sql_password: str) -> bool:
    checkpoint("verify-sql", "START")

    # Permit only the current operator public IP in addition to Azure services.
    ipcp = run(["curl", "-fsSL", "https://api.ipify.org"], timeout=30)
    if ipcp.returncode == 0 and ipcp.stdout.strip():
        ip = ipcp.stdout.strip()
        run(
            [
                "az", "sql", "server", "firewall-rule", "create",
                "--resource-group", runtime["resource_group"],
                "--server", runtime["sql_server"],
                "--name", "AllowTechScopeOperator",
                "--start-ip-address", ip,
                "--end-ip-address", ip,
                "--only-show-errors", "-o", "none",
            ],
            timeout=90,
        )

    env = os.environ.copy()
    env["TECHSCOPE_SQL_SERVER"] = runtime["sql_server_fqdn"]
    env["TECHSCOPE_SQL_DATABASE"] = runtime["sql_database"]
    env["TECHSCOPE_SQL_USER"] = sql_user
    env["TECHSCOPE_SQL_PASSWORD"] = sql_password

    # uv creates an isolated ephemeral environment; the password is supplied only
    # through the child-process environment and never persisted in the repository.
    cp = run(
        [
            "uv", "run",
            "--with", "pymssql",
            "python", str(ROOT / "tools" / "p1d_sql_verify.py"),
        ],
        env=env,
        timeout=300,
        secret=True,
    )

    success = cp.returncode == 0
    counts: dict[str, Any] = {}
    if success:
        try:
            counts = json.loads(cp.stdout.strip().splitlines()[-1])
        except Exception:
            success = False

    output_pass = bool(
        success
        and int(counts.get("technology", 0)) > 0
        and int(counts.get("category", 0)) > 0
        and int(counts.get("view_count", 0)) == 3
    )

    write_json(ROOT / "evidence" / "azure-sql" / "p1d-execution.json", {
        "component": "CMP_AZURE_SQL",
        "status": "PASS" if success else "FAIL",
        "server": runtime["sql_server"],
        "database": runtime["sql_database"],
        "timestamp": now(),
        "secret_material": "NOT_STORED",
        "error": None if success else (cp.stderr or cp.stdout)[-1000:],
    })
    write_json(ROOT / "evidence" / "azure-sql" / "p1d-output.json", {
        "component": "CMP_AZURE_SQL",
        "status": "PASS" if output_pass else "FAIL",
        "row_counts": counts,
        "timestamp": now(),
    })
    checkpoint("verify-sql", "PASS" if output_pass else "FAIL")
    return output_pass

def finalize(runtime: dict[str, Any] | None, results: dict[str, str], blockers: list[str]) -> int:
    write_json(COMPONENTS, {
        "timestamp": now(),
        "components": results,
        "blockers": blockers,
    })
    summary = {
        "timestamp": now(),
        "status": "PASS" if not blockers and all(v == "PASS" for v in results.values()) else "PENDING",
        "components": results,
        "blockers": blockers,
        "runtime": runtime or {},
        "cost_note": "Azure resources remain allocated after this run. Databricks job compute is ephemeral; Azure SQL Basic and other resources continue billing until deleted.",
        "cleanup_resource_group": (runtime or {}).get("resource_group"),
    }
    write_json(SUMMARY, summary)
    print(f"P1D_CLOUD_DATA_E2E={summary['status']}")
    print("P1D_COMPONENTS=" + json.dumps(results, ensure_ascii=False))
    print(f"BLOCKER_COUNT={len(blockers)}")
    if runtime:
        print(f"RESOURCE_GROUP={runtime['resource_group']}")
        print(f"P1D_LOCATION={runtime['location']}")
    print(f"SUMMARY={SUMMARY.relative_to(ROOT)}")
    print("SECRETS_WRITTEN_TO_REPO=NO")
    return 0

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    account = az_json(["account", "show"], timeout=60)
    subscription_id = account["id"]
    suffix = hashlib.sha256(subscription_id.encode()).hexdigest()[:8]
    sql_user = "techscopeadmin"
    sql_password = random_sql_password()

    print("P1D_PLAN=ADLS+ADF+DatabricksWorkspace+AzureSQLBasic")
    print("P1D_COST=USAGE_BASED_ADLS_ADF + DATABRICKS_EPHEMERAL_COMPUTE + AZURE_SQL_BASIC_PERSISTENT")
    print("P1D_EXPECTED_TIME=15-40_MINUTES")
    print("P1D_LONGEST_STAGE=DATABRICKS_WORKSPACE_AND_JOB_COMPUTE")
    print("P1D_USER_INPUT_EXPECTED=NONE")
    print("P1D_DO_NOT_INTERRUPT_DURING=PROVISION,RUN_DATABRICKS")

    if not args.execute:
        print("P1D_PLAN_ONLY=PASS")
        return 0

    results = {
        "CMP_ADLS": "PENDING",
        "CMP_ADF": "PENDING",
        "CMP_DATABRICKS": "PENDING",
        "CMP_AZURE_SQL": "PENDING",
    }
    blockers: list[str] = []
    runtime = None

    try:
        location = stage_gate(cfg, suffix, sql_user, sql_password)
        runtime = provision(location, suffix, sql_user, sql_password)
        results["CMP_ADLS"] = "PASS"

        storage_key = upload_structured(runtime)

        if run_adf(runtime):
            results["CMP_ADF"] = "PASS"
        else:
            blockers.append("ADF pipeline execution/output verification")

        if run_databricks(runtime, storage_key, sql_user, sql_password):
            results["CMP_DATABRICKS"] = "PASS"
            if verify_sql(runtime, sql_user, sql_password):
                results["CMP_AZURE_SQL"] = "PASS"
            else:
                blockers.append("Azure SQL direct verification")
        else:
            blockers.append("Databricks workspace/job compute execution")
            blockers.append("Azure SQL load depends on Databricks P1D job")

    except Exception as exc:
        blockers.append(str(exc)[:1200])
        checkpoint("p1d", "FAIL", str(exc)[:300])

    return finalize(runtime, results, blockers)

if __name__ == "__main__":
    raise SystemExit(main())
