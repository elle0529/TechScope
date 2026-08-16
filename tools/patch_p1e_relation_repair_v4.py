from pathlib import Path

P = Path("/workspaces/TechScope/tools/p1e_relation_repair.py")
text = P.read_text(encoding="utf-8")

old = r'''    # Prefer current LTS non-ML runtimes.  Fall back to any non-ML runtime.
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
'''

new = r'''    # This workspace has legacy access and legacy DBFS disabled.
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
'''

if old in text:
    text = text.replace(old, new, 1)
elif "DATABRICKS_RUNTIME_POLICY=MIN_13_3_NON_ML_LTS_PREFERRED" not in text:
    raise RuntimeError("V3_RUNTIME_SELECTION_BLOCK_NOT_FOUND")

P.write_text(text, encoding="utf-8")
print("P1E_V4_DBR_MIN_VERSION_PATCH=PASS")
