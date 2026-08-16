from pathlib import Path

P = Path("/workspaces/TechScope/tools/p1e_relation_repair.py")
text = P.read_text(encoding="utf-8")

old_jobs = '''    jobs_obj = run_json(
        ["databricks", "jobs", "list", "--expand-tasks", "-o", "json"],
        timeout=60,
    )
    jobs = jobs_obj.get("jobs", jobs_obj if isinstance(jobs_obj, list) else [])
'''

new_jobs = '''    jobs_obj = run_json(
        ["databricks", "jobs", "list", "--expand-tasks", "-o", "json"],
        timeout=60,
    )
    if isinstance(jobs_obj, list):
        jobs = jobs_obj
    elif isinstance(jobs_obj, dict):
        jobs = jobs_obj.get("jobs", [])
    else:
        jobs = []
'''

old_clusters = '''        clusters_obj = run_json(
            ["databricks", "clusters", "list", "-o", "json"],
            timeout=60,
        )
        clusters = clusters_obj.get(
            "clusters",
            clusters_obj if isinstance(clusters_obj, list) else [],
        )
'''

new_clusters = '''        clusters_obj = run_json(
            ["databricks", "clusters", "list", "-o", "json"],
            timeout=60,
        )
        if isinstance(clusters_obj, list):
            clusters = clusters_obj
        elif isinstance(clusters_obj, dict):
            clusters = clusters_obj.get("clusters", [])
        else:
            clusters = []
'''

if old_jobs in text:
    text = text.replace(old_jobs, new_jobs, 1)
elif "if isinstance(jobs_obj, list):" not in text:
    raise RuntimeError("JOBS_LIST_PATCH_MARKER_NOT_FOUND")

if old_clusters in text:
    text = text.replace(old_clusters, new_clusters, 1)
elif "if isinstance(clusters_obj, list):" not in text:
    raise RuntimeError("CLUSTERS_LIST_PATCH_MARKER_NOT_FOUND")

P.write_text(text, encoding="utf-8")
print("P1E_V2_JSON_SHAPE_PATCH=PASS")
