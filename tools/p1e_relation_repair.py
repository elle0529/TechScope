#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
RELATION = ROOT / "extractor/output/relation.csv"
ALIAS_SRC = ROOT / "databricks/config/technology_alias.csv"
DBX_NOTEBOOK_SRC = ROOT / "databricks/p1e_relation_repair_task.py"

GEN = ROOT / "generated/p1e_relation_repair"
RESULT = ROOT / "results/latest/p1e-relation-repair.json"
SILVER_LOCAL = GEN / "technology_relation.csv"
GOLD_LOCAL = GEN / "fact_technology_relation.csv"
DIM_LOCAL = GEN / "dim_technology.csv"
ALIAS_LOCAL = GEN / "technology_alias_normalized.csv"

EVD_DBX_EXEC = ROOT / "evidence/databricks/p1e-relation-execution.json"
EVD_DBX_OUT = ROOT / "evidence/databricks/p1e-relation-output.json"
EVD_SQL = ROOT / "evidence/azure-sql/p1e-relation-load.json"

DBX_BASE = "/Shared/TechScope/P1E_Relation_Repair"
STORAGE_ACCOUNT = "sttechscopedev239bd206"
FILESYSTEM = "techscope"
SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"


def run(cmd, *, check=True, timeout=None):
    cp = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-5000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-5000:]
        )
    return cp


def run_json(cmd, *, timeout=None):
    cp = run(cmd, timeout=timeout)
    text = (cp.stdout or "").strip()
    if not text:
        raise RuntimeError("EMPTY_JSON_OUTPUT: " + " ".join(cmd))
    return json.loads(text)


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def sql_connect():
    from mssql_python import connect

    cs = (
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    return connect(cs)


def export_dim_technology():
    conn = sql_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TechnologyId, TechnologyName
            FROM techscope.DimTechnology
            ORDER BY TechnologyId
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise RuntimeError("DIM_TECHNOLOGY_EMPTY")

    ensure_parent(DIM_LOCAL)
    with DIM_LOCAL.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["TechnologyId", "TechnologyName"])
        w.writerows(rows)
    return len(rows)


def _relation_name_norm(value):
    import re
    s = str(value or "").strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _relation_semantic_norm(value):
    stop = {
        "microsoft", "azure",
        "service", "services",
        "database", "analytics",
    }
    tokens = [
        t for t in _relation_name_norm(value).split()
        if t not in stop
    ]
    return " ".join(tokens)


def normalize_aliases():
    import csv
    import re

    with DIM_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        dim_rows = list(csv.DictReader(f))

    canon_names = [
        (r["TechnologyId"], (r["TechnologyName"] or "").strip())
        for r in dim_rows
        if (r.get("TechnologyId") or "").strip()
        and (r.get("TechnologyName") or "").strip()
    ]

    hint_groups = {
        "ADF": ["Azure Data Factory", "ADF"],
        "SSAS": [
            "SQL Server Analysis Services",
            "Microsoft SQL Server Analysis Services",
            "SSAS",
        ],
        "Synapse": [
            "Azure Synapse Analytics",
            "Azure Synapse",
            "Synapse",
        ],
        "Power BI": ["Microsoft Power BI", "Power BI"],
        "Teams": ["Microsoft Teams", "Teams"],
        "Azure SQL": [
            "Azure SQL Database",
            "Microsoft Azure SQL Database",
            "Azure SQL",
        ],
        "Cosmos DB": [
            "Azure Cosmos DB",
            "Microsoft Azure Cosmos DB",
            "Cosmos DB",
        ],
        "Data Lake Gen2": [
            "Azure Data Lake Storage Gen2",
            "ADLS Gen2",
            "Data Lake Gen2",
        ],
        "ADLS Gen2": [
            "Azure Data Lake Storage Gen2",
            "ADLS Gen2",
            "Data Lake Gen2",
        ],
        "Analysis Service": [
            "Azure Analysis Services",
            "Analysis Services",
            "Analysis Service",
        ],
        "Analysis Services": [
            "Azure Analysis Services",
            "Analysis Services",
        ],
        "Azure ML": [
            "Azure Machine Learning",
            "Microsoft Azure Machine Learning",
            "Azure ML",
        ],
        "Azure OpenAI": [
            "Azure OpenAI Service",
            "Microsoft Azure OpenAI",
            "Azure OpenAI",
        ],
        "Power Apps": ["Microsoft Power Apps", "Power Apps"],
        "Power Automate": ["Microsoft Power Automate", "Power Automate"],
        "Power Virtual Agents": [
            "Microsoft Power Virtual Agents",
            "Power Virtual Agents",
            "PVA",
        ],
        "Embedded BI": [
            "Power BI Embedded",
            "Microsoft Power BI Embedded",
            "Embedded BI",
        ],
        "Brain Portal": ["Brain Portal"],
        "Data Mart": ["Data Mart", "Datamart"],
        "Azure AI Search": [
            "Azure AI Search",
            "Azure Cognitive Search",
        ],
        "AI Search": [
            "Azure AI Search",
            "Azure Cognitive Search",
            "AI Search",
        ],
        "Databricks": ["Azure Databricks", "Databricks"],
        "Azure Databricks": ["Azure Databricks", "Databricks"],
        "Azure Functions": ["Azure Functions", "Functions"],
        "Logic Apps": ["Azure Logic Apps", "Logic Apps"],
        "API Management": [
            "Azure API Management",
            "API Management",
            "APIM",
        ],
    }

    def choose_canonical(alias, hints):
        alias_raw = _relation_name_norm(alias)
        alias_sem = _relation_semantic_norm(alias)
        scored = []

        for tid, cname in canon_names:
            c_raw = _relation_name_norm(cname)
            c_sem = _relation_semantic_norm(cname)
            score = 0

            if alias_raw and alias_raw == c_raw:
                score = max(score, 100)
            if alias_sem and alias_sem == c_sem:
                score = max(score, 95)

            for hint in hints:
                h_raw = _relation_name_norm(hint)
                h_sem = _relation_semantic_norm(hint)

                if h_raw and h_raw == c_raw:
                    score = max(score, 100)
                if h_sem and h_sem == c_sem:
                    score = max(score, 95)

                if h_sem and len(h_sem) >= 4:
                    if h_sem in c_sem or c_sem in h_sem:
                        score = max(score, 80)

            if score:
                extra = abs(
                    len(c_sem.split()) -
                    min(
                        [len(_relation_semantic_norm(x).split()) for x in hints if x]
                        or [len(alias_sem.split())]
                    )
                )
                scored.append((score, -extra, -len(cname), tid, cname))

        if not scored:
            return None

        scored.sort(reverse=True)
        best = scored[0]
        tied = [x for x in scored if x[:3] == best[:3]]
        if len({x[4] for x in tied}) > 1:
            return None
        return best[4]

    aliases = set()

    if ALIAS_SRC.exists():
        with ALIAS_SRC.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            lower = {h.lower(): h for h in headers}

            alias_col = None
            canon_col = None

            for candidate in [
                "alias", "technology_alias", "alias_name",
                "source_name", "raw_name",
            ]:
                if candidate in lower:
                    alias_col = lower[candidate]
                    break

            for candidate in [
                "canonical_name", "technology_name",
                "canonical", "target_name",
            ]:
                if candidate in lower:
                    canon_col = lower[candidate]
                    break

            canonical_set = {name for _, name in canon_names}

            if alias_col and canon_col:
                for row in reader:
                    a = (row.get(alias_col) or "").strip()
                    c = (row.get(canon_col) or "").strip()
                    if a and c in canonical_set and a != c:
                        aliases.add((a, c))

    for alias, hints in hint_groups.items():
        canonical = choose_canonical(alias, hints)
        if canonical and alias != canonical:
            aliases.add((alias, canonical))

    with RELATION.open("r", encoding="utf-8-sig", newline="") as f:
        relation_rows = list(csv.DictReader(f))

    source_tokens = set()
    for row in relation_rows:
        flow = (row.get("flow_fragment_raw") or "").strip()
        if not flow:
            continue

        tmp = flow
        for sep in ["→", "->", "⇒", "➜", "⟶", "=>", "—>", "/", "·", "+", ",", "|"]:
            tmp = tmp.replace(sep, "\n")

        for token in tmp.splitlines():
            token = re.sub(r"\s+", " ", token).strip()
            token = re.sub(
                r"(에\s*공급|저장.?통합|분석\s*구조|분석|운영|연동|통합|활용|기반|처리)$",
                "",
                token,
            ).strip()

            if 2 <= len(token) <= 80:
                source_tokens.add(token)

    for token in source_tokens:
        t_sem = _relation_semantic_norm(token)
        if len(t_sem) < 3:
            continue

        matches = []
        for _, cname in canon_names:
            c_sem = _relation_semantic_norm(cname)
            if t_sem == c_sem:
                matches.append(cname)

        if len(set(matches)) == 1 and token != matches[0]:
            aliases.add((token, matches[0]))

    normalized = sorted(
        aliases,
        key=lambda x: (x[1].lower(), x[0].lower()),
    )

    ensure_parent(ALIAS_LOCAL)
    with ALIAS_LOCAL.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alias", "canonical_name"])
        w.writerows(normalized)

    return len(normalized)


def local_relation_preflight():
    import csv
    import re

    with DIM_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        dim_rows = list(csv.DictReader(f))

    name_to_id = {
        (r["TechnologyName"] or "").strip(): (r["TechnologyId"] or "").strip()
        for r in dim_rows
        if (r.get("TechnologyName") or "").strip()
        and (r.get("TechnologyId") or "").strip()
    }

    terms = []
    for name, tid in name_to_id.items():
        if len(name) >= 3:
            terms.append((name.lower(), tid, name))

    with ALIAS_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            alias = (r.get("alias") or "").strip()
            canonical = (r.get("canonical_name") or "").strip()
            tid = name_to_id.get(canonical)

            if alias and tid:
                terms.append((alias.lower(), tid, canonical))

    terms = sorted(
        {(a, tid, c) for a, tid, c in terms},
        key=lambda x: (-len(x[0]), x[0]),
    )

    arrow_re = re.compile(r"\s*(?:→|->|⇒|➜|⟶|=>|—>)\s*")

    def mentions(segment):
        low = segment.lower()
        found = []
        occupied = []

        for term, tid, canonical in terms:
            start = 0
            while True:
                idx = low.find(term, start)
                if idx < 0:
                    break

                end = idx + len(term)
                overlap = any(
                    not (end <= a or idx >= b)
                    for a, b in occupied
                )

                if not overlap:
                    occupied.append((idx, end))
                    found.append((idx, tid, canonical))

                start = idx + max(1, len(term))

        found.sort(key=lambda x: x[0])

        result = []
        seen = set()

        for _, tid, canonical in found:
            if tid not in seen:
                result.append((tid, canonical))
                seen.add(tid)

        return result

    resolved = set()
    resolved_fragments = 0
    unresolved_fragments = 0
    sample = []

    with RELATION.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        flow = (row.get("flow_fragment_raw") or "").strip()
        source_id = (row.get("source_id") or "").strip()

        parts = [p.strip() for p in arrow_re.split(flow) if p.strip()]

        if len(parts) < 2:
            unresolved_fragments += 1
            continue

        part_mentions = [mentions(p) for p in parts]
        local_count = 0

        for i in range(len(parts) - 1):
            left = part_mentions[i]
            right = part_mentions[i + 1]

            if not left or not right:
                continue

            for src_id, src_name in left:
                for dst_id, dst_name in right:
                    if src_id == dst_id:
                        continue

                    key = (
                        src_id,
                        dst_id,
                        "flows_to",
                        "DIRECT",
                        source_id,
                    )
                    resolved.add(key)
                    local_count += 1

                    if len(sample) < 12:
                        sample.append(
                            f"{src_id}:{src_name} -> {dst_id}:{dst_name}"
                        )

        if local_count:
            resolved_fragments += 1
        else:
            unresolved_fragments += 1

    return {
        "rows": len(resolved),
        "resolved_fragments": resolved_fragments,
        "unresolved_fragments": unresolved_fragments,
        "sample": sample,
    }

def relation_row_count():
    with RELATION.open("r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def workspace_import(local: Path, remote: str, *, source_notebook=False):
    cmd = [
        "databricks", "workspace", "import", remote,
        "--file", str(local),
        "--overwrite",
    ]
    if source_notebook:
        cmd += ["--format", "SOURCE", "--language", "PYTHON"]
    else:
        cmd += ["--format", "AUTO"]
    run(cmd, timeout=60)



def _as_list(obj, key):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        value = obj.get(key, [])
        return value if isinstance(value, list) else []
    return []


def _version_tuple(value):
    import re
    nums = re.findall(r"\\d+", str(value or ""))
    return tuple(int(x) for x in nums[:3]) if nums else (0,)


def discover_ephemeral_job_compute():
    # Ask the workspace for what it can actually launch now instead of
    # hard-coding an obsolete DBR or Azure VM SKU.
    versions_obj = run_json(
        ["databricks", "clusters", "spark-versions", "-o", "json"],
        timeout=60,
    )
    nodes_obj = run_json(
        ["databricks", "clusters", "list-node-types", "-o", "json"],
        timeout=60,
    )

    versions = _as_list(versions_obj, "versions")
    nodes = _as_list(nodes_obj, "node_types")

    if not versions:
        raise RuntimeError("DATABRICKS_SPARK_VERSIONS_EMPTY")
    if not nodes:
        raise RuntimeError("DATABRICKS_NODE_TYPES_EMPTY")

    # This workspace has legacy access and legacy DBFS disabled.
    # Databricks rejects DBR < 13.3 before cluster startup in that mode.
    # Enforce the workspace-supported floor explicitly.
    import re

    def dbr_major_minor(v):
        key = str(v.get("key") or "")
        m = re.match(r"^\s*(\d+)\.(\d+)", key)
        if not m:
            return (0, 0)
        return (int(m.group(1)), int(m.group(2)))

    eligible = []
    for v in versions:
        key = str(v.get("key") or "")
        name = str(v.get("name") or "")
        low = (key + " " + name).lower()
        ver = dbr_major_minor(v)

        is_ml = (
            "machine learning" in low
            or " ml " in (" " + low + " ")
            or "-ml-" in low
            or low.endswith("-ml")
        )
        is_gpu = "gpu" in low

        if ver < (13, 3):
            continue
        if is_ml or is_gpu:
            continue
        eligible.append(v)

    if not eligible:
        available = [
            {
                "key": str(v.get("key") or ""),
                "name": str(v.get("name") or ""),
            }
            for v in versions[:30]
        ]
        raise RuntimeError(
            "NO_SUPPORTED_DBR_13_3_OR_ABOVE="
            + str(available)
        )

    def supported_runtime_key(v):
        key = str(v.get("key") or "")
        name = str(v.get("name") or "")
        low = (key + " " + name).lower()
        is_lts = "lts" in low
        return (
            1 if is_lts else 0,
            dbr_major_minor(v),
            key,
        )

    # Prefer the newest available non-ML LTS at or above 13.3.
    chosen_runtime = sorted(
        eligible,
        key=supported_runtime_key,
        reverse=True,
    )[0]

    if not chosen_runtime.get("key"):
        raise RuntimeError("DATABRICKS_RUNTIME_SELECTION_FAIL")

    print(
        "DATABRICKS_RUNTIME_POLICY=MIN_13_3_NON_ML_LTS_PREFERRED",
        flush=True,
    )

    # Avoid GPU/HPC SKUs and deprecated entries.  For this 77-row Spark job,
    # prefer the smallest ordinary Azure VM that still has >=4 cores and
    # >=8 GiB RAM.  If the workspace exposes only other shapes, fall back to
    # the smallest non-GPU/non-deprecated shape.
    preferred_ids = [
        "Standard_D4ds_v5",
        "Standard_D4s_v5",
        "Standard_D4as_v5",
        "Standard_D4s_v3",
        "Standard_DS3_v2",
        "Standard_D3_v2",
    ]

    usable = []
    for n in nodes:
        nid = str(n.get("node_type_id") or "")
        low = nid.lower()
        if not nid:
            continue
        if n.get("is_deprecated") is True:
            continue
        if any(x in low for x in [
            "standard_nc", "standard_nd", "standard_nv",
            "gpu", "inf", "hb", "hc"
        ]):
            continue

        cores = float(n.get("num_cores") or 0)
        mem = float(n.get("memory_mb") or 0)
        usable.append((n, cores, mem))

    if not usable:
        raise RuntimeError("DATABRICKS_NO_USABLE_NODE_TYPE")

    chosen_node = None
    for pid in preferred_ids:
        for n, cores, mem in usable:
            if n.get("node_type_id") == pid:
                chosen_node = n
                break
        if chosen_node:
            break

    if chosen_node is None:
        roomy = [
            (n, cores, mem) for n, cores, mem in usable
            if cores >= 4 and mem >= 8192
        ]
        pool = roomy or usable
        pool.sort(
            key=lambda x: (
                x[1] if x[1] > 0 else 999999,
                x[2] if x[2] > 0 else 999999999,
                str(x[0].get("node_type_id")),
            )
        )
        chosen_node = pool[0][0]

    spec = {
        "spark_version": chosen_runtime["key"],
        "node_type_id": chosen_node["node_type_id"],
        "num_workers": 1,
        "runtime_engine": "STANDARD",
    }

    print(
        "DATABRICKS_EPHEMERAL_RUNTIME="
        + str(chosen_runtime["key"]),
        flush=True,
    )
    print(
        "DATABRICKS_EPHEMERAL_NODE_TYPE="
        + str(chosen_node["node_type_id"]),
        flush=True,
    )
    print("DATABRICKS_EPHEMERAL_WORKERS=1", flush=True)

    return {
        "kind": "new_cluster",
        "spec": spec,
        "source_job_id": None,
        "source_job_name": "AUTO_DISCOVERED_EPHEMERAL_JOB_COMPUTE",
    }

def discover_compute():
    jobs_obj = run_json(
        ["databricks", "jobs", "list", "--expand-tasks", "-o", "json"],
        timeout=60,
    )
    if isinstance(jobs_obj, list):
        jobs = jobs_obj
    elif isinstance(jobs_obj, dict):
        jobs = jobs_obj.get("jobs", [])
    else:
        jobs = []

    # Prefer the already-proven TechScope job cluster definition.
    ordered = sorted(
        jobs,
        key=lambda j: (
            0 if "techscope" in str(j.get("settings", {}).get("name", "")).lower() else 1,
            -int(j.get("created_time", 0) or 0),
        ),
    )

    for job in ordered:
        job_id = job.get("job_id")
        details = job
        if job_id:
            try:
                details = run_json(
                    ["databricks", "jobs", "get", str(job_id), "-o", "json"],
                    timeout=60,
                )
            except Exception:
                pass

        settings = details.get("settings", {})
        for task in settings.get("tasks", []) or []:
            nc = task.get("new_cluster")
            if nc and nc.get("spark_version") and nc.get("node_type_id"):
                nc = dict(nc)
                # Automated job clusters reject these interactive-only fields.
                nc.pop("autotermination_minutes", None)
                nc.pop("cluster_name", None)
                return {
                    "kind": "new_cluster",
                    "spec": nc,
                    "source_job_id": job_id,
                    "source_job_name": settings.get("name"),
                }

            ec = task.get("existing_cluster_id")
            if ec:
                return {
                    "kind": "existing_cluster_id",
                    "cluster_id": ec,
                    "source_job_id": job_id,
                    "source_job_name": settings.get("name"),
                }

    # Fallback: use a currently running interactive cluster only.
    try:
        clusters_obj = run_json(
            ["databricks", "clusters", "list", "-o", "json"],
            timeout=60,
        )
        if isinstance(clusters_obj, list):
            clusters = clusters_obj
        elif isinstance(clusters_obj, dict):
            clusters = clusters_obj.get("clusters", [])
        else:
            clusters = []
        for c in clusters:
            if c.get("state") == "RUNNING" and c.get("cluster_id"):
                return {
                    "kind": "existing_cluster_id",
                    "cluster_id": c["cluster_id"],
                    "source_job_id": None,
                    "source_job_name": None,
                }
    except Exception:
        pass

    print(
        "DATABRICKS_REUSABLE_COMPUTE=NONE "
        "ACTION=AUTO_DISCOVER_EPHEMERAL_JOB_COMPUTE",
        flush=True,
    )
    return discover_ephemeral_job_compute()


def submit_job(compute):
    task = {
        "task_key": "p1e_relation_repair",
        "notebook_task": {
            "notebook_path": f"{DBX_BASE}/p1e_relation_repair_task",
            "source": "WORKSPACE",
        },
        "timeout_seconds": 900,
    }

    if compute["kind"] == "new_cluster":
        task["new_cluster"] = compute["spec"]
    elif compute["kind"] == "existing_cluster_id":
        task["existing_cluster_id"] = compute["cluster_id"]
    elif compute["kind"] == "serverless":
        # No new_cluster / existing_cluster_id: supported notebook task
        # is executed with Databricks-managed serverless compute.
        pass
    else:
        raise RuntimeError(
            "UNKNOWN_DATABRICKS_COMPUTE_KIND="
            + str(compute.get("kind"))
        )

    body = {
        "run_name": "TechScope-P1E-Relation-Repair",
        "tasks": [task],
        "timeout_seconds": 900,
    }

    submit_path = GEN / "databricks-submit.json"
    submit_path.write_text(
        json.dumps(body, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    obj = run_json(
        [
            "databricks", "jobs", "submit",
            "--json", f"@{submit_path}",
            "--no-wait",
            "-o", "json",
        ],
        timeout=60,
    )
    run_id = obj.get("run_id")
    if not run_id:
        raise RuntimeError(f"DATABRICKS_SUBMIT_NO_RUN_ID={obj}")
    return int(run_id)


def wait_for_run(run_id: int):
    deadline = time.time() + 10 * 60
    last_state = None

    while time.time() < deadline:
        obj = run_json(
            ["databricks", "jobs", "get-run", str(run_id), "-o", "json"],
            timeout=60,
        )
        state = obj.get("state", {})
        life = state.get("life_cycle_state")
        result = state.get("result_state")
        message = state.get("state_message")

        signature = (life, result, message)
        if signature != last_state:
            print(
                f"DATABRICKS_RUN_STATE={life} "
                f"RESULT={result or '-'}",
                flush=True,
            )
            last_state = signature

        if life in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            if result != "SUCCESS":
                raise RuntimeError(
                    f"DATABRICKS_RUN_FAILED run_id={run_id} "
                    f"life={life} result={result} message={message}"
                )
            tasks = obj.get("tasks", []) or []
            if not tasks:
                raise RuntimeError("DATABRICKS_RUN_HAS_NO_TASKS")
            task_run_id = tasks[0].get("run_id")
            if not task_run_id:
                raise RuntimeError("DATABRICKS_TASK_RUN_ID_MISSING")
            return obj, int(task_run_id)

        print("DATABRICKS_RUN=WAITING", flush=True)
        time.sleep(20)

    raise TimeoutError(
        f"DATABRICKS_RUN_TIMEOUT run_id={run_id} max_seconds=600"
    )


def get_notebook_result(task_run_id: int):
    obj = run_json(
        [
            "databricks", "jobs", "get-run-output",
            str(task_run_id), "-o", "json",
        ],
        timeout=60,
    )
    result = (obj.get("notebook_output") or {}).get("result")
    if not result:
        raise RuntimeError(
            "DATABRICKS_NOTEBOOK_RESULT_EMPTY: "
            + json.dumps(obj, ensure_ascii=False)[:3000]
        )
    payload = json.loads(result)
    if payload.get("status") != "PASS":
        raise RuntimeError(f"DATABRICKS_PAYLOAD_FAIL={payload}")
    return payload


def validate_payload(payload):
    relations = payload.get("relations") or []
    if not relations:
        raise RuntimeError("NO_RELATIONS_RETURNED_FROM_DATABRICKS")

    with DIM_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        dim_ids = {
            r["TechnologyId"]
            for r in csv.DictReader(f)
        }

    invalid = []
    for r in relations:
        if (
            r["SourceTechnologyId"] not in dim_ids
            or r["TargetTechnologyId"] not in dim_ids
            or r["SourceTechnologyId"] == r["TargetTechnologyId"]
            or r["EvidenceType"] != "DIRECT"
            or r["RelationType"] != "flows_to"
            or not r["SourceId"]
        ):
            invalid.append(r)

    if invalid:
        raise RuntimeError(
            "RELATION_QUALITY_GATE_FAIL="
            + json.dumps(invalid[:10], ensure_ascii=False)
        )

    expected = int(payload.get("validated_relation_rows", 0))
    if expected != len(relations):
        raise RuntimeError(
            f"RELATION_COUNT_MISMATCH expected={expected} actual={len(relations)}"
        )

    return relations


def write_outputs(relations, payload):
    ensure_parent(SILVER_LOCAL)

    # Silver and Gold have intentionally explicit schemas.
    with SILVER_LOCAL.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source_technology_id",
                "target_technology_id",
                "relation_type",
                "evidence_type",
                "source_id",
                "resolution_status",
            ]
        )
        for r in relations:
            w.writerow(
                [
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                    "RESOLVED",
                ]
            )

    with GOLD_LOCAL.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "SourceTechnologyId",
                "TargetTechnologyId",
                "RelationType",
                "EvidenceType",
                "SourceId",
            ]
        )
        for r in relations:
            w.writerow(
                [
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                ]
            )

    unresolved_path = GEN / "unresolved_relation_fragments.json"
    unresolved_path.write_text(
        json.dumps(
            payload.get("unresolved_sample", []),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def upload_adls(local: Path, remote_path: str):
    run(
        [
            "az", "storage", "fs", "file", "upload",
            "--account-name", STORAGE_ACCOUNT,
            "--file-system", FILESYSTEM,
            "--path", remote_path,
            "--source", str(local),
            "--auth-mode", "login",
            "--overwrite",
            "true",
            "--only-show-errors",
        ],
        timeout=120,
    )


def load_sql(relations):
    conn = sql_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation"
        )
        before = int(cur.fetchone()[0])

        cur.execute(
            "SELECT TechnologyId FROM techscope.DimTechnology"
        )
        valid_ids = {r[0] for r in cur.fetchall()}

        invalid_fk = [
            r for r in relations
            if r["SourceTechnologyId"] not in valid_ids
            or r["TargetTechnologyId"] not in valid_ids
        ]
        if invalid_fk:
            raise RuntimeError(
                f"SQL_FK_PREFLIGHT_FAIL={len(invalid_fk)}"
            )

        inserted = 0
        for r in relations:
            cur.execute(
                """
                IF NOT EXISTS (
                    SELECT 1
                    FROM techscope.FactTechnologyRelation
                    WHERE SourceTechnologyId=?
                      AND TargetTechnologyId=?
                      AND RelationType=?
                      AND EvidenceType=?
                      AND SourceId=?
                )
                BEGIN
                    INSERT INTO techscope.FactTechnologyRelation
                    (
                        SourceTechnologyId,
                        TargetTechnologyId,
                        RelationType,
                        EvidenceType,
                        SourceId
                    )
                    VALUES (?,?,?,?,?)
                END
                """,
                (
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                    r["SourceTechnologyId"],
                    r["TargetTechnologyId"],
                    r["RelationType"],
                    r["EvidenceType"],
                    r["SourceId"],
                ),
            )
            # mssql-python rowcount on IF blocks is not dependable; calculate later.

        conn.commit()

        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation"
        )
        after = int(cur.fetchone()[0])
        inserted = max(0, after - before)

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactTechnologyRelation f
            LEFT JOIN techscope.DimTechnology s
              ON s.TechnologyId=f.SourceTechnologyId
            LEFT JOIN techscope.DimTechnology t
              ON t.TechnologyId=f.TargetTechnologyId
            WHERE s.TechnologyId IS NULL OR t.TechnologyId IS NULL
            """
        )
        invalid_after = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactTechnologyRelation
            WHERE SourceTechnologyId=TargetTechnologyId
            """
        )
        self_edges = int(cur.fetchone()[0])

        if after <= 0 or invalid_after != 0 or self_edges != 0:
            raise RuntimeError(
                "SQL_POSTLOAD_QUALITY_FAIL "
                f"after={after} invalid_fk={invalid_after} "
                f"self_edges={self_edges}"
            )

        return {
            "before": before,
            "after": after,
            "inserted": inserted,
            "invalid_fk_rows": invalid_after,
            "self_edges": self_edges,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def write_json(path: Path, obj):
    ensure_parent(path)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    print("P1E_RELATION_REPAIR=START", flush=True)

    if not RELATION.exists():
        raise RuntimeError(f"RELATION_FILE_NOT_FOUND={RELATION}")
    if not DBX_NOTEBOOK_SRC.exists():
        raise RuntimeError(f"DATABRICKS_NOTEBOOK_NOT_FOUND={DBX_NOTEBOOK_SRC}")

    GEN.mkdir(parents=True, exist_ok=True)

    raw_count = relation_row_count()
    print(f"RAW_RELATION_ROWS={raw_count}", flush=True)
    if raw_count != 77:
        print(
            f"RAW_RELATION_ROWS_NOTICE=EXPECTED_77_ACTUAL_{raw_count}",
            flush=True,
        )

    dim_count = export_dim_technology()
    alias_count = normalize_aliases()
    print(f"DIM_TECHNOLOGY_ROWS={dim_count}", flush=True)
    print(f"NORMALIZED_ALIAS_ROWS={alias_count}", flush=True)

    preflight = local_relation_preflight()
    print(
        f"LOCAL_RELATION_PREFLIGHT_ROWS={preflight['rows']}",
        flush=True,
    )
    print(
        f"LOCAL_RESOLVED_FRAGMENTS={preflight['resolved_fragments']}",
        flush=True,
    )
    print(
        f"LOCAL_UNRESOLVED_FRAGMENTS={preflight['unresolved_fragments']}",
        flush=True,
    )

    for item in preflight["sample"][:8]:
        print("LOCAL_RELATION_SAMPLE=" + item, flush=True)

    if preflight["rows"] <= 0:
        raise RuntimeError(
            "LOCAL_RELATION_PREFLIGHT_ZERO: Databricks job not submitted"
        )

    # Authentication preflight before any cloud mutation.
    me = run_json(
        ["databricks", "current-user", "me", "-o", "json"],
        timeout=45,
    )
    print(
        "DATABRICKS_AUTH=PASS USER="
        + str(me.get("userName") or me.get("user_name") or "authenticated"),
        flush=True,
    )

    run(
        ["databricks", "workspace", "mkdirs", f"{DBX_BASE}/inputs"],
        timeout=60,
    )

    workspace_import(
        RELATION,
        f"{DBX_BASE}/inputs/relation.csv",
    )
    workspace_import(
        DIM_LOCAL,
        f"{DBX_BASE}/inputs/dim_technology.csv",
    )
    workspace_import(
        ALIAS_LOCAL,
        f"{DBX_BASE}/inputs/technology_alias_normalized.csv",
    )
    workspace_import(
        DBX_NOTEBOOK_SRC,
        f"{DBX_BASE}/p1e_relation_repair_task",
        source_notebook=True,
    )
    print("DATABRICKS_WORKSPACE_STAGE=PASS", flush=True)

    # Classic compute cannot start because the subscription currently has
    # no free Korea Central regional vCPU quota.  This workspace/region
    # supports serverless Jobs, so use Databricks-managed compute directly.
    compute = {
        "kind": "serverless",
        "source_job_id": None,
        "source_job_name": "SERVERLESS_JOB_COMPUTE",
    }
    print(
        "DATABRICKS_COMPUTE=serverless SOURCE_JOB=SERVERLESS_JOB_COMPUTE",
        flush=True,
    )

    run_id = submit_job(compute)
    print(f"DATABRICKS_RUN_ID={run_id}", flush=True)

    run_meta, task_run_id = wait_for_run(run_id)
    payload = get_notebook_result(task_run_id)
    relations = validate_payload(payload)

    print("DATABRICKS_RELATION_RESOLUTION=PASS", flush=True)
    print(
        f"RESOLVED_FRAGMENTS={payload['resolved_fragments']}",
        flush=True,
    )
    print(
        f"UNRESOLVED_FRAGMENTS={payload['unresolved_fragments']}",
        flush=True,
    )
    print(
        f"VALIDATED_RELATION_ROWS={payload['validated_relation_rows']}",
        flush=True,
    )
    print(
        f"SPARK_PARTITIONS={payload['partition_before']}->"
        f"{payload['partition_after']}",
        flush=True,
    )

    write_outputs(relations, payload)

    silver_adls = "silver/technology_relation/technology_relation.csv"
    gold_adls = "gold/fact_technology_relation/fact_technology_relation.csv"

    upload_adls(SILVER_LOCAL, silver_adls)
    upload_adls(GOLD_LOCAL, gold_adls)
    print("ADLS_SILVER_RELATION=PASS", flush=True)
    print("ADLS_GOLD_RELATION=PASS", flush=True)

    sql_result = load_sql(relations)
    print(
        f"FACT_TECHNOLOGY_RELATION_ROWS="
        f"{sql_result['before']}->{sql_result['after']}",
        flush=True,
    )
    print(
        f"FACT_TECHNOLOGY_RELATION_INSERTED={sql_result['inserted']}",
        flush=True,
    )
    print("SQL_RELATION_FK_VALIDATION=PASS", flush=True)
    print("SQL_RELATION_SELF_EDGE_VALIDATION=PASS", flush=True)

    now = datetime.now(timezone.utc).isoformat()

    write_json(
        EVD_DBX_EXEC,
        {
            "timestamp_utc": now,
            "component": "CMP_DATABRICKS",
            "phase": "P1E_RELATION_REPAIR",
            "implementation_evidence": "EXECUTION",
            "databricks_run_id": run_id,
            "databricks_task_run_id": task_run_id,
            "compute": compute,
            "raw_relation_rows": raw_count,
            "resolved_fragments": payload["resolved_fragments"],
            "unresolved_fragments": payload["unresolved_fragments"],
            "validated_relation_rows": payload["validated_relation_rows"],
            "partition_before": payload["partition_before"],
            "partition_after": payload["partition_after"],
            "result": "PASS",
        },
    )

    write_json(
        EVD_DBX_OUT,
        {
            "timestamp_utc": now,
            "component": "CMP_DATABRICKS",
            "phase": "P1E_RELATION_REPAIR",
            "implementation_evidence": "OUTPUT",
            "silver": {
                "adls_path": f"{FILESYSTEM}/{silver_adls}",
                "rows": len(relations),
            },
            "gold": {
                "adls_path": f"{FILESYSTEM}/{gold_adls}",
                "rows": len(relations),
            },
            "aggregates": payload.get("aggregates", []),
            "result": "PASS",
        },
    )

    write_json(
        EVD_SQL,
        {
            "timestamp_utc": now,
            "component": "CMP_AZURE_SQL",
            "phase": "P1E_RELATION_REPAIR",
            "implementation_evidence": "OUTPUT",
            "table": "techscope.FactTechnologyRelation",
            **sql_result,
            "result": "PASS",
        },
    )

    summary = {
        "timestamp_utc": now,
        "status": "PASS",
        "raw_relation_rows": raw_count,
        "resolved_fragments": payload["resolved_fragments"],
        "unresolved_fragments": payload["unresolved_fragments"],
        "validated_relation_rows": len(relations),
        "fact_rows_before": sql_result["before"],
        "fact_rows_after": sql_result["after"],
        "fact_rows_inserted": sql_result["inserted"],
        "silver_adls": silver_adls,
        "gold_adls": gold_adls,
        "databricks_run_id": run_id,
        "unresolved_sample": payload.get("unresolved_sample", []),
    }
    write_json(RESULT, summary)

    # Preserve frozen architecture; lint is verification only.
    lint = run(
        ["python", str(ROOT / "tools/architecture_lint.py")],
        check=False,
        timeout=90,
    )
    lint_text = (lint.stdout or "") + "\n" + (lint.stderr or "")
    if lint.returncode != 0 or "ARCHITECTURE_LINT=PASS" not in lint_text:
        print("ARCHITECTURE_LINT_AFTER_REPAIR=FAIL", flush=True)
        print(lint_text[-4000:], flush=True)
        raise RuntimeError("ARCHITECTURE_LINT_AFTER_REPAIR=FAIL")

    print("ARCHITECTURE_LINT_AFTER_REPAIR=PASS", flush=True)
    print("P1E_RELATION_REPAIR=PASS", flush=True)
    print(
        "REPORT=results/latest/p1e-relation-repair.json",
        flush=True,
    )
    print("NEXT_ACTION=P3_COSMOS_FEEDBACK", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(
            f"P1E_RELATION_REPAIR=FAIL "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        raise
