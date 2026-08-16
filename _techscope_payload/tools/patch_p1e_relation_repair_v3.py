from pathlib import Path

P = Path("/workspaces/TechScope/tools/p1e_relation_repair.py")
text = P.read_text(encoding="utf-8")

helper = r'''
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

    # Prefer current LTS non-ML runtimes.  Fall back to any non-ML runtime.
    def runtime_key(v):
        key = str(v.get("key") or "")
        name = str(v.get("name") or "")
        low = (key + " " + name).lower()
        is_lts = "lts" in low
        is_ml = (
            "machine learning" in low
            or " ml " in (" " + low + " ")
            or "-ml-" in low
            or low.endswith("-ml")
        )
        return (1 if is_lts and not is_ml else 0,
                1 if not is_ml else 0,
                _version_tuple(key))

    versions = sorted(versions, key=runtime_key, reverse=True)
    chosen_runtime = None
    for v in versions:
        low = (str(v.get("key",""))+" "+str(v.get("name",""))).lower()
        if "gpu" in low:
            continue
        chosen_runtime = v
        break

    if not chosen_runtime or not chosen_runtime.get("key"):
        raise RuntimeError("DATABRICKS_RUNTIME_SELECTION_FAIL")

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
'''

marker = "\ndef discover_compute():\n"
if "def discover_ephemeral_job_compute():" not in text:
    if marker not in text:
        raise RuntimeError("DISCOVER_COMPUTE_MARKER_NOT_FOUND")
    text = text.replace(marker, "\n" + helper + marker, 1)

old_raise = '''    raise RuntimeError(
        "NO_REUSABLE_DATABRICKS_COMPUTE: existing TechScope job cluster "
        "definition or running cluster was not found"
    )
'''

new_fallback = '''    print(
        "DATABRICKS_REUSABLE_COMPUTE=NONE "
        "ACTION=AUTO_DISCOVER_EPHEMERAL_JOB_COMPUTE",
        flush=True,
    )
    return discover_ephemeral_job_compute()
'''

if old_raise in text:
    text = text.replace(old_raise, new_fallback, 1)
elif "ACTION=AUTO_DISCOVER_EPHEMERAL_JOB_COMPUTE" not in text:
    raise RuntimeError("COMPUTE_FALLBACK_PATCH_MARKER_NOT_FOUND")

# The new compute can legitimately take longer to provision.
text = text.replace(
    "deadline = time.time() + 12 * 60",
    "deadline = time.time() + 15 * 60",
)
text = text.replace(
    "max_seconds=720",
    "max_seconds=900",
)

P.write_text(text, encoding="utf-8")
print("P1E_V3_EPHEMERAL_COMPUTE_PATCH=PASS")
