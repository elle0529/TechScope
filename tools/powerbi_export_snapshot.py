from __future__ import annotations

import csv
from pathlib import Path
from mssql_python import connect

OUT = Path("/workspaces/TechScope/powerbi/demo_snapshot/data")
OUT.mkdir(parents=True, exist_ok=True)

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)

EXPORTS = {
    "ExecutiveSummary.csv": """
        SELECT
            TotalTechnologies, Categories, Companies, DirectClaims,
            IndirectClaims, ArchitectureLayers, AIRequests,
            SuccessfulRequests, CitationRequests, AvgLatencyMs
        FROM techscope.PbiExecutiveSummary
    """,
    "TechnologyExplorer.csv": """
        SELECT
            TechnologyKey, TechnologyId, TechnologyName, CategoryName,
            ArchitectureLayer, LayerOrder, EvidenceType, SourceId
        FROM techscope.PbiTechnologyExplorer
        ORDER BY TechnologyKey
    """,
    "AIRequestDetail.csv": """
        SELECT
            RequestKey, RequestTimestamp, Status, LatencyMs,
            RetrievedChunkCount, CitationFlag, FeedbackScore, ModelName
        FROM techscope.vwPbiAIRequestDetail
        ORDER BY RequestKey
    """,
    "GroundedTechnology.csv": """
        SELECT
            TechnologyId, TechnologyName, GroundedRequestCount
        FROM techscope.vwPbiGroundedTechnology
        ORDER BY GroundedRequestCount DESC, TechnologyName
    """,
}

conn = connect(CS)
try:
    cur = conn.cursor()
    counts = {}
    for filename, sql in EXPORTS.items():
        cur.execute(sql)
        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
        path = OUT / filename
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        counts[filename] = len(rows)
        print(f"SNAPSHOT_EXPORT={filename} ROWS={len(rows)}")

    assert counts["ExecutiveSummary.csv"] == 1
    assert counts["TechnologyExplorer.csv"] == 515
    assert counts["AIRequestDetail.csv"] >= 1
    assert counts["GroundedTechnology.csv"] >= 1
finally:
    conn.close()

print("POWER_BI_SNAPSHOT_EXPORT=PASS")
print("SNAPSHOT_SOURCE=LIVE_AZURE_SQL")
print("FAKE_ROWS_INSERTED=NO")
