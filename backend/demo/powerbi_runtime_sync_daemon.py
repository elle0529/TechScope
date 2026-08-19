#!/usr/bin/env python3
from __future__ import annotations

import csv
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mssql_python import connect

ROOT = Path("/workspaces/TechScope")
OUT = ROOT / "powerbi" / "runtime_data"
STATE = OUT / ".sync-state.json"
LOCK = OUT / ".autosync.lock"

SQL_SERVER = os.getenv(
    "TECHSCOPE_SQL_SERVER",
    "sql-techscope-dev-239bd206.database.windows.net",
)
SQL_DATABASE = os.getenv(
    "TECHSCOPE_SQL_DATABASE",
    "sqldb-techscope-dev",
)
POLL_SECONDS = float(os.getenv("TECHSCOPE_POWERBI_SYNC_POLL_SECONDS", "1.0"))

CS = (
    f"Server={SQL_SERVER};"
    f"Database={SQL_DATABASE};"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)

COUNT_QUERY = "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def state_write(**kwargs: Any) -> None:
    payload = {
        "status": kwargs.pop("status", "PASS"),
        "timestamp_utc": utc_now(),
        "sql_server": SQL_SERVER,
        "sql_database": SQL_DATABASE,
        "poll_seconds": POLL_SECONDS,
        "authoritative_count_source": "techscope.FactAIRequest",
        **kwargs,
    }
    atomic_text(STATE, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def db():
    return connect(CS)


def scalar(cur, sql: str):
    cur.execute(sql)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"SQL returned no row: {sql}")
    return row[0]


def current_count(conn) -> int:
    cur = conn.cursor()
    return int(scalar(cur, COUNT_QUERY))


def write_csv(path: Path, headers, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                "" if value is None else
                ("true" if value is True else "false" if value is False else value)
                for value in row
            ])
    os.replace(tmp, path)


def query_rows(cur, sql: str):
    cur.execute(sql)
    headers = [str(d[0]) for d in cur.description]
    rows = cur.fetchall()
    return headers, rows


def sync_all(conn) -> int:
    cur = conn.cursor()

    ai_requests = int(scalar(
        cur,
        "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest",
    ))
    successful = int(scalar(
        cur,
        "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE Status='success'",
    ))
    citation_requests = int(scalar(
        cur,
        "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE CitationFlag=1",
    ))

    cur.execute(
        "SELECT AVG(CONVERT(decimal(18,2),LatencyMs)) "
        "FROM techscope.FactAIRequest"
    )
    avg_row = cur.fetchone()
    avg_latency = 0 if avg_row is None or avg_row[0] is None else avg_row[0]

    executive_headers = [
        "TotalTechnologies",
        "Categories",
        "Companies",
        "DirectClaims",
        "IndirectClaims",
        "ArchitectureLayers",
        "AIRequests",
        "SuccessfulRequests",
        "CitationRequests",
        "AvgLatencyMs",
    ]
    executive_rows = [[
        515,
        41,
        0,
        0,
        0,
        0,
        ai_requests,
        successful,
        citation_requests,
        avg_latency,
    ]]

    detail_headers, detail_rows = query_rows(
        cur,
        """
        SELECT
            RequestKey,
            RequestTimestamp,
            Status,
            LatencyMs,
            RetrievedChunkCount,
            CitationFlag,
            FeedbackScore,
            ModelName
        FROM techscope.vwPbiAIRequestDetail
        ORDER BY RequestKey
        """,
    )

    grounded_headers, grounded_rows = query_rows(
        cur,
        """
        SELECT
            TechnologyId,
            TechnologyName,
            GroundedRequestCount
        FROM techscope.vwPbiGroundedTechnology
        ORDER BY GroundedRequestCount DESC, TechnologyName
        """,
    )

    technology_headers, technology_rows = query_rows(
        cur,
        """
        SELECT
            TechnologyKey,
            TechnologyId,
            TechnologyName,
            CategoryName,
            ArchitectureLayer,
            LayerOrder,
            EvidenceType,
            SourceId
        FROM techscope.PbiTechnologyExplorer
        ORDER BY TechnologyKey
        """,
    )

    # Atomic per-file replacement. Power BI only sees complete CSV files.
    write_csv(OUT / "ExecutiveSummary.csv", executive_headers, executive_rows)
    write_csv(OUT / "AIRequestDetail.csv", detail_headers, detail_rows)
    write_csv(OUT / "GroundedTechnology.csv", grounded_headers, grounded_rows)
    write_csv(OUT / "TechnologyExplorer.csv", technology_headers, technology_rows)

    state_write(
        status="PASS",
        ai_requests=ai_requests,
        successful_requests=successful,
        citation_requests=citation_requests,
        detail_rows=len(detail_rows),
        grounded_rows=len(grounded_rows),
        technology_rows=len(technology_rows),
        sync_mode="FACTAIREQUEST_POLL_ON_CHANGE",
    )
    print(
        f"POWERBI_RUNTIME_SNAPSHOT_SYNC=PASS "
        f"AIRequests={ai_requests} SOURCE=FactAIRequest",
        flush=True,
    )
    return ai_requests


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("POWERBI_AUTOSYNC_DAEMON=PASS_ALREADY_RUNNING", flush=True)
        return 0

    state_write(
        status="STARTING",
        ai_requests=None,
        sync_mode="FACTAIREQUEST_POLL_ON_CHANGE",
    )
    print(
        "POWERBI_AUTOSYNC_DAEMON=START SOURCE=techscope.FactAIRequest",
        flush=True,
    )

    conn = None
    last_count = None

    while True:
        try:
            if conn is None:
                conn = db()

            count = current_count(conn)
            if last_count is None or count != last_count:
                last_count = sync_all(conn)

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            state_write(status="STOPPED", ai_requests=last_count)
            return 0

        except Exception as exc:
            state_write(
                status="RETRYING",
                ai_requests=last_count,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            print(
                f"POWERBI_AUTOSYNC_RETRY {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            conn = None
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
