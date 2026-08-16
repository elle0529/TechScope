from __future__ import annotations

from mssql_python import connect

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def fetch_scalar(cur, sql: str, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Expected scalar result")
    return row[0]


conn = connect(CS)
try:
    cur = conn.cursor()

    table_exists = int(
        fetch_scalar(
            cur,
            "SELECT CASE WHEN OBJECT_ID(N'techscope.DimTechnology',N'U') "
            "IS NOT NULL THEN 1 ELSE 0 END",
        )
    )
    if table_exists != 1:
        raise RuntimeError("techscope.DimTechnology is missing")

    cur.execute(
        """
        SELECT c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID(N'techscope.DimTechnology')
        ORDER BY c.column_id
        """
    )
    before = [str(row[0]) for row in cur.fetchall()]
    print("DIM_TECHNOLOGY_COLUMNS_BEFORE=" + ",".join(before))

    if "TechnologyId" not in before:
        raise RuntimeError("DimTechnology.TechnologyId is missing")

    total = int(fetch_scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.DimTechnology"))
    distinct_domain = int(
        fetch_scalar(
            cur,
            "SELECT COUNT_BIG(*) FROM "
            "(SELECT TechnologyId FROM techscope.DimTechnology "
            "GROUP BY TechnologyId) d",
        )
    )

    if total != 515:
        raise RuntimeError(f"Expected 515 DimTechnology rows, got {total}")
    if distinct_domain != total:
        raise RuntimeError(
            f"TechnologyId uniqueness failed: rows={total}, distinct={distinct_domain}"
        )

    # Live schema drift repair: add only the missing surrogate key.
    if "TechnologyKey" not in before:
        print("DIM_TECHNOLOGY_SURROGATE_KEY=ADD_START")
        cur.execute(
            "ALTER TABLE techscope.DimTechnology "
            "ADD TechnologyKey bigint IDENTITY(1,1) NOT NULL"
        )
        conn.commit()
        print("DIM_TECHNOLOGY_SURROGATE_KEY=ADD_PASS")
    else:
        print("DIM_TECHNOLOGY_SURROGATE_KEY=REUSE")

    surrogate_now = int(
        fetch_scalar(
            cur,
            "SELECT COUNT_BIG(*) FROM "
            "(SELECT TechnologyKey FROM techscope.DimTechnology "
            "GROUP BY TechnologyKey) s",
        )
    )
    if surrogate_now != 515:
        raise RuntimeError(
            f"TechnologyKey post-resume uniqueness failed: {surrogate_now}"
        )
    print("DIM_TECHNOLOGY_SURROGATE_RESUME_PROOF=PASS KEYS=515")

    uq_exists = int(
        fetch_scalar(
            cur,
            """
            SELECT CASE WHEN EXISTS(
                SELECT 1
                FROM sys.key_constraints kc
                WHERE kc.parent_object_id = OBJECT_ID(?)
                  AND kc.[type] = ?
                  AND kc.[name] = ?
            ) THEN 1 ELSE 0 END
            """,
            (
                "techscope.DimTechnology",
                "UQ",
                "UQ_DimTechnology_TechnologyKey",
            ),
        )
    )
    if uq_exists == 0:
        cur.execute(
            "ALTER TABLE techscope.DimTechnology "
            "ADD CONSTRAINT UQ_DimTechnology_TechnologyKey "
            "UNIQUE (TechnologyKey)"
        )
        conn.commit()
        print("DIM_TECHNOLOGY_SURROGATE_UNIQUE=ADD_PASS")
    else:
        print("DIM_TECHNOLOGY_SURROGATE_UNIQUE=REUSE")

    fact_exists = int(
        fetch_scalar(
            cur,
            "SELECT CASE WHEN OBJECT_ID(N'techscope.FactAIRequest',N'U') "
            "IS NOT NULL THEN 1 ELSE 0 END",
        )
    )
    if fact_exists == 0:
        cur.execute(
            """
            CREATE TABLE techscope.FactAIRequest(
                RequestKey bigint IDENTITY(1,1) NOT NULL
                    CONSTRAINT PK_FactAIRequest PRIMARY KEY,
                RequestId uniqueidentifier NOT NULL
                    CONSTRAINT UQ_FactAIRequest_RequestId UNIQUE,
                RequestTimestamp datetime2(3) NOT NULL,
                Status varchar(32) NOT NULL,
                LatencyMs int NULL,
                RetrievedChunkCount int NOT NULL,
                CitationFlag bit NOT NULL,
                FeedbackScore tinyint NULL,
                ErrorType nvarchar(128) NULL,
                ModelName nvarchar(128) NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IX_FactAIRequest_Timestamp "
            "ON techscope.FactAIRequest(RequestTimestamp)"
        )
        conn.commit()
        print("FACT_AI_REQUEST=CREATE_PASS")
    else:
        print("FACT_AI_REQUEST=REUSE")

    bridge_exists = int(
        fetch_scalar(
            cur,
            "SELECT CASE WHEN "
            "OBJECT_ID(N'techscope.BridgeAIRequestTechnology',N'U') "
            "IS NOT NULL THEN 1 ELSE 0 END",
        )
    )
    if bridge_exists == 0:
        cur.execute(
            """
            CREATE TABLE techscope.BridgeAIRequestTechnology(
                RequestKey bigint NOT NULL,
                TechnologyKey bigint NOT NULL,
                CONSTRAINT PK_BridgeAIRequestTechnology
                    PRIMARY KEY(RequestKey, TechnologyKey),
                CONSTRAINT FK_BridgeAIRequestTechnology_Request
                    FOREIGN KEY(RequestKey)
                    REFERENCES techscope.FactAIRequest(RequestKey),
                CONSTRAINT FK_BridgeAIRequestTechnology_Technology
                    FOREIGN KEY(TechnologyKey)
                    REFERENCES techscope.DimTechnology(TechnologyKey)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IX_BridgeAIRequestTechnology_Technology "
            "ON techscope.BridgeAIRequestTechnology"
            "(TechnologyKey, RequestKey)"
        )
        conn.commit()
        print("BRIDGE_AI_REQUEST_TECHNOLOGY=CREATE_PASS")
    else:
        print("BRIDGE_AI_REQUEST_TECHNOLOGY=REUSE")

    # CREATE OR ALTER VIEW is executed as its own batch.
    cur.execute(
        """
        CREATE OR ALTER VIEW techscope.vwAIRequestSummary AS
        SELECT
            CAST(RequestTimestamp AS date) AS RequestDate,
            COUNT_BIG(*) AS RequestCount,
            SUM(CASE WHEN Status = 'success'
                     THEN CONVERT(bigint,1)
                     ELSE CONVERT(bigint,0) END) AS SuccessCount,
            SUM(CASE WHEN CitationFlag = 1
                     THEN CONVERT(bigint,1)
                     ELSE CONVERT(bigint,0) END) AS CitationRequestCount,
            AVG(CONVERT(decimal(18,2), LatencyMs)) AS AvgLatencyMs,
            AVG(CONVERT(decimal(18,2), RetrievedChunkCount))
                AS AvgRetrievedChunkCount,
            AVG(CONVERT(decimal(18,2), FeedbackScore))
                AS AvgFeedbackScore
        FROM techscope.FactAIRequest
        GROUP BY CAST(RequestTimestamp AS date)
        """
    )
    conn.commit()
    print("VW_AI_REQUEST_SUMMARY=PASS")

    cur.execute(
        """
        CREATE OR ALTER VIEW techscope.vwGroundedRequestsByTechnology AS
        SELECT
            t.TechnologyId,
            t.TechnologyName,
            COUNT_BIG(DISTINCT b.RequestKey) AS GroundedRequestCount
        FROM techscope.BridgeAIRequestTechnology b
        JOIN techscope.DimTechnology t
          ON t.TechnologyKey = b.TechnologyKey
        GROUP BY t.TechnologyId, t.TechnologyName
        """
    )
    conn.commit()
    print("VW_GROUNDED_REQUESTS_BY_TECHNOLOGY=PASS")

    cur.execute(
        """
        SELECT c.name
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID(N'techscope.DimTechnology')
        ORDER BY c.column_id
        """
    )
    after = [str(row[0]) for row in cur.fetchall()]
    print("DIM_TECHNOLOGY_COLUMNS_AFTER=" + ",".join(after))

    total_after = int(
        fetch_scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.DimTechnology")
    )
    surrogate_count = int(
        fetch_scalar(
            cur,
            "SELECT COUNT_BIG(*) FROM "
            "(SELECT TechnologyKey FROM techscope.DimTechnology "
            "GROUP BY TechnologyKey) s",
        )
    )

    object_checks = []
    for obj, typ in (
        ("techscope.FactAIRequest", "U"),
        ("techscope.BridgeAIRequestTechnology", "U"),
        ("techscope.vwAIRequestSummary", "V"),
        ("techscope.vwGroundedRequestsByTechnology", "V"),
    ):
        object_checks.append(
            int(
                fetch_scalar(
                    cur,
                    f"SELECT CASE WHEN OBJECT_ID(N'{obj}',N'{typ}') "
                    "IS NOT NULL THEN 1 ELSE 0 END",
                )
            )
        )

finally:
    conn.close()

assert "TechnologyKey" in after
assert total_after == 515
assert surrogate_count == 515
assert object_checks == [1, 1, 1, 1], object_checks

print("DIM_TECHNOLOGY_ROW_PRESERVATION=PASS ROWS=515")
print("DIM_TECHNOLOGY_DOMAIN_ID_UNIQUENESS=PASS")
print("DIM_TECHNOLOGY_SURROGATE_KEY=PASS")
print("FACT_AI_REQUEST=PASS")
print("BRIDGE_AI_REQUEST_TECHNOLOGY=PASS")
print("P2C_SQL_SCHEMA_RECONCILIATION=PASS")
print("P2C_SQL_MIGRATION=PASS")
