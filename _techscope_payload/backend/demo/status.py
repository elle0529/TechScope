from __future__ import annotations

from mssql_python import connect

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def get_demo_status() -> dict:
    conn = connect(CS)
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT_BIG(*) FROM techscope.DimTechnology")
        technology_count = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT_BIG(DISTINCT CategoryName)
            FROM techscope.DimTechnology
            WHERE CategoryName IS NOT NULL
              AND LTRIM(RTRIM(CategoryName)) <> ''
            """
        )
        category_count = int(cur.fetchone()[0])

        cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
        ai_request_count = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT TOP (1)
                RequestKey,
                RequestTimestamp,
                Status,
                LatencyMs,
                RetrievedChunkCount,
                CitationFlag,
                ModelName
            FROM techscope.FactAIRequest
            ORDER BY RequestKey DESC
            """
        )
        row = cur.fetchone()

        latest = None
        if row:
            latest = {
                "request_key": int(row[0]),
                "request_timestamp": str(row[1]),
                "status": str(row[2] or ""),
                "latency_ms": int(row[3]) if row[3] is not None else None,
                "retrieved_chunk_count": int(row[4]) if row[4] is not None else None,
                "citation": bool(row[5]) if row[5] is not None else False,
                "model_name": str(row[6] or ""),
            }

        return {
            "technology_count": technology_count,
            "category_count": category_count,
            "ai_request_count": ai_request_count,
            "latest_request": latest,
        }
    finally:
        conn.close()
