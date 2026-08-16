from __future__ import annotations

import csv
from pathlib import Path

from mssql_python import connect

ROOT = Path("/workspaces/TechScope/powerbi")
TARGETS = [
    ROOT / "demo_snapshot" / "data",
    ROOT / "demo_final" / "data",
]

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def _write_csv(path: Path, headers: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def sync_powerbi_snapshot() -> dict:
    conn = connect(CS)
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
        ai_requests = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactAIRequest
            WHERE Status='success'
            """
        )
        successful = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(*)
            FROM techscope.FactAIRequest
            WHERE CitationFlag=1
            """
        )
        citation_requests = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT AVG(CONVERT(decimal(18,2),LatencyMs))
            FROM techscope.FactAIRequest
            """
        )
        avg_latency = cur.fetchone()[0] or 0

        cur.execute(
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
            """
        )
        detail_headers = [d[0] for d in cur.description]
        detail_rows = cur.fetchall()

        cur.execute(
            """
            SELECT
                TechnologyId,
                TechnologyName,
                GroundedRequestCount
            FROM techscope.vwPbiGroundedTechnology
            ORDER BY GroundedRequestCount DESC, TechnologyName
            """
        )
        grounded_headers = [d[0] for d in cur.description]
        grounded_rows = cur.fetchall()

        synced = []
        for target in TARGETS:
            if not target.parent.exists():
                continue

            executive = target / "ExecutiveSummary.csv"
            existing = {}
            existing_headers = []

            if executive.exists():
                with executive.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    existing_headers = list(reader.fieldnames or [])
                    row = next(reader, None)
                    if row:
                        existing = dict(row)

            required = [
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
            headers = existing_headers or required
            for h in required:
                if h not in headers:
                    headers.append(h)

            existing.setdefault("TotalTechnologies", "515")
            existing.setdefault("Categories", "41")
            existing.setdefault("Companies", "0")
            existing.setdefault("DirectClaims", "0")
            existing.setdefault("IndirectClaims", "0")
            existing.setdefault("ArchitectureLayers", "0")

            existing["AIRequests"] = str(ai_requests)
            existing["SuccessfulRequests"] = str(successful)
            existing["CitationRequests"] = str(citation_requests)
            existing["AvgLatencyMs"] = str(avg_latency)

            _write_csv(
                executive,
                headers,
                [[existing.get(h, "") for h in headers]],
            )
            _write_csv(target / "AIRequestDetail.csv", detail_headers, detail_rows)
            _write_csv(target / "GroundedTechnology.csv", grounded_headers, grounded_rows)
            synced.append(str(target))

        if not synced:
            raise RuntimeError("No Power BI snapshot target directories found")

        return {
            "status": "PASS",
            "ai_request_count": ai_requests,
            "successful_requests": successful,
            "citation_requests": citation_requests,
            "avg_latency_ms": float(avg_latency),
            "detail_rows": len(detail_rows),
            "grounded_rows": len(grounded_rows),
            "targets": synced,
        }
    finally:
        conn.close()
