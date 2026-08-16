#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print("P1D_V4_STATIC_VALIDATION=FAIL " + msg)
    raise SystemExit(1)


def main() -> int:
    orch = ROOT / "tools" / "p1d_cloud_data_e2e.py"
    resume = ROOT / "tools" / "p1d_resume_databricks_sql.py"
    for path in [orch, resume, ROOT / "tools" / "p1d_sql_verify.py", ROOT / "tools" / "sync_p1d_docs.py"]:
        if not path.exists():
            fail("missing=" + str(path.relative_to(ROOT)))

    text = orch.read_text(encoding="utf-8-sig")
    if "autotermination_minutes" in text:
        fail("automated_job_cluster_autotermination_regression")
    if 'heartbeat_label="DATABRICKS_JOB"' not in text:
        fail("databricks_job_heartbeat_missing")
    if "candidates.sort(key=version_tuple, reverse=True)" not in text:
        fail("dynamic_latest_lts_selection_missing")

    r = resume.read_text(encoding="utf-8-sig")
    for token in [
        "P1D_RESUME_PROVISION=SKIP_REUSE",
        "P1D_RESUME_ADF=SKIP_ALREADY_PASS",
        '"az", "sql", "server", "update"',
        "run_databricks",
        "verify_sql",
    ]:
        if token not in r:
            fail("resume_contract=" + token)

    print("AUTOMATED_CLUSTER_AUTOTERMINATION_REMOVED=PASS")
    print("LATEST_SUPPORTED_LTS_DYNAMIC_SELECTION=PASS")
    print("DATABRICKS_JOB_HEARTBEAT=PASS")
    print("RESUME_ONLY_SCOPE=PASS")
    print("P1D_V4_STATIC_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
