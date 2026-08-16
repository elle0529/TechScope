from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient
from mssql_python import connect

REPO = Path("/workspaces/TechScope")
CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)

def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return None if row is None else row[0]

def object_exists(cur, name: str, kind: str = "U") -> bool:
    return int(scalar(
        cur,
        "SELECT CASE WHEN OBJECT_ID(?, ?) IS NOT NULL THEN 1 ELSE 0 END",
        (name, kind),
    )) == 1

def seed_ai_if_needed() -> int:
    conn = connect(CS)
    try:
        cur = conn.cursor()
        count = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"))
    finally:
        conn.close()

    target = 3
    needed = max(0, target - count)
    print(f"AI_REQUESTS_EXISTING={count}")
    print(f"AI_REQUESTS_NEEDED_FOR_DEMO={needed}")

    if needed == 0:
        return count

    from backend.app.main import app

    questions = [
        "What role does Azure Databricks play in TechScope? Include authoritative technology IDs.",
        "How does Azure Data Factory move structured data into the TechScope bronze layer? Include authoritative technology IDs.",
        "How are Azure AI Search and Azure OpenAI used together in TechScope? Include authoritative technology IDs.",
    ]

    client = TestClient(app)
    for idx in range(needed):
        print(f"DEMO_AI_SEED_REQUEST={idx+1}_OF_{needed}")
        response = client.post("/ask", json={"question": questions[idx % len(questions)]})
        print(f"DEMO_AI_SEED_STATUS={response.status_code}")
        if response.status_code != 200:
            raise RuntimeError(response.text)
        body = response.json()
        if not body.get("grounded") or not body.get("citations"):
            raise RuntimeError("Demo seed response was not grounded with citations")

    conn = connect(CS)
    try:
        cur = conn.cursor()
        final_count = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"))
    finally:
        conn.close()
    print(f"AI_REQUESTS_AFTER_SEED={final_count}")
    return final_count

def load_architecture_mapping(cur, conn):
    cur.execute("""
    IF OBJECT_ID(N'techscope.PbiArchitectureMapping',N'U') IS NULL
    CREATE TABLE techscope.PbiArchitectureMapping(
        TechnologyId varchar(64) NOT NULL,
        ArchitectureLayer nvarchar(256) NOT NULL,
        LayerOrder int NULL,
        EvidenceType nvarchar(64) NULL,
        CONSTRAINT PK_PbiArchitectureMapping PRIMARY KEY(TechnologyId, ArchitectureLayer)
    )
    """)
    conn.commit()
    cur.execute("DELETE FROM techscope.PbiArchitectureMapping")
    conn.commit()

    mappings: dict[tuple[str, str], tuple[int | None, str | None]] = {}

    # Preferred: Databricks-produced RAG knowledge chunks, because IDs are already resolved.
    rag_candidates = [
        REPO / "generated" / "knowledge_chunks.jsonl",
        REPO / "rag" / "knowledge_chunks.jsonl",
    ]
    for path in rag_candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ids = row.get("technology_ids") or []
            layers = row.get("architecture_layer") or []
            evidence = row.get("evidence_type")
            if isinstance(ids, str):
                ids = [ids]
            if isinstance(layers, str):
                layers = [layers]
            for tid in ids:
                for layer in layers or ["Unmapped"]:
                    tid = str(tid).strip()
                    layer = str(layer).strip()
                    if tid and layer and layer != "Unmapped":
                        mappings[(tid, layer)] = (None, str(evidence) if evidence else None)
        if mappings:
            print(f"ARCHITECTURE_MAPPING_SOURCE={path}")
            break

    # Fallback: original source-derived architecture_mapping.csv.
    if not mappings:
        path = REPO / "extractor" / "output" / "architecture_mapping.csv"
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            for row in rows:
                norm = {str(k).strip().lower(): v for k, v in row.items()}
                tech = str(norm.get("technology") or "").strip()
                layer = str(norm.get("architecture_layer") or "").strip()
                if not tech or not layer:
                    continue
                cur.execute(
                    "SELECT TechnologyId FROM techscope.DimTechnology "
                    "WHERE LOWER(LTRIM(RTRIM(TechnologyName))) = LOWER(?)",
                    (tech,),
                )
                found = cur.fetchone()
                if found:
                    raw_order = str(norm.get("layer_order") or "").strip()
                    try:
                        order = int(raw_order) if raw_order else None
                    except ValueError:
                        order = None
                    ev = str(norm.get("evidence_type") or "").strip() or None
                    mappings[(str(found[0]), layer)] = (order, ev)
            if mappings:
                print(f"ARCHITECTURE_MAPPING_SOURCE={path}")

    if mappings:
        for (tid, layer), (order, ev) in sorted(mappings.items()):
            cur.execute(
                "INSERT INTO techscope.PbiArchitectureMapping"
                "(TechnologyId,ArchitectureLayer,LayerOrder,EvidenceType) "
                "VALUES(?,?,?,?)",
                (tid, layer, order, ev),
            )
        conn.commit()

    print(f"ARCHITECTURE_MAPPING_ROWS={len(mappings)}")
    return len(mappings)

def prepare_sql():
    conn = connect(CS)
    try:
        cur = conn.cursor()

        tech_count = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.DimTechnology"))
        if tech_count != 515:
            raise RuntimeError(f"Expected 515 technologies, got {tech_count}")

        mapping_rows = load_architecture_mapping(cur, conn)

        cur.execute("""
        IF OBJECT_ID(N'techscope.PbiTechnologyExplorer',N'U') IS NULL
        CREATE TABLE techscope.PbiTechnologyExplorer(
            TechnologyKey bigint NOT NULL,
            TechnologyId varchar(64) NOT NULL,
            TechnologyName nvarchar(512) NOT NULL,
            CategoryName nvarchar(512) NULL,
            ArchitectureLayer nvarchar(256) NOT NULL,
            LayerOrder int NULL,
            EvidenceType nvarchar(64) NULL,
            SourceId varchar(64) NULL,
            CONSTRAINT PK_PbiTechnologyExplorer PRIMARY KEY(TechnologyKey)
        )
        """)
        conn.commit()
        cur.execute("DELETE FROM techscope.PbiTechnologyExplorer")
        conn.commit()

        cur.execute("""
        ;WITH OneLayer AS(
            SELECT TechnologyId, ArchitectureLayer, LayerOrder, EvidenceType,
                   ROW_NUMBER() OVER(
                       PARTITION BY TechnologyId
                       ORDER BY CASE WHEN LayerOrder IS NULL THEN 1 ELSE 0 END,
                                LayerOrder, ArchitectureLayer
                   ) AS rn
            FROM techscope.PbiArchitectureMapping
        )
        INSERT INTO techscope.PbiTechnologyExplorer(
            TechnologyKey, TechnologyId, TechnologyName, CategoryName,
            ArchitectureLayer, LayerOrder, EvidenceType, SourceId
        )
        SELECT
            t.TechnologyKey,
            t.TechnologyId,
            t.TechnologyName,
            t.CategoryName,
            COALESCE(m.ArchitectureLayer, N'Unmapped'),
            m.LayerOrder,
            m.EvidenceType,
            t.SourceId
        FROM techscope.DimTechnology t
        LEFT JOIN OneLayer m
          ON m.TechnologyId=t.TechnologyId AND m.rn=1
        """)
        conn.commit()

        explorer_count = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.PbiTechnologyExplorer"))
        if explorer_count != 515:
            raise RuntimeError(f"Technology Explorer expected 515 rows, got {explorer_count}")

        # Live AI report views
        cur.execute("""
        CREATE OR ALTER VIEW techscope.vwPbiAIRequestDetail AS
        SELECT RequestKey,RequestTimestamp,Status,LatencyMs,RetrievedChunkCount,
               CitationFlag,FeedbackScore,ModelName
        FROM techscope.FactAIRequest
        """)
        conn.commit()

        cur.execute("""
        CREATE OR ALTER VIEW techscope.vwPbiGroundedTechnology AS
        SELECT t.TechnologyId,t.TechnologyName,
               COUNT_BIG(DISTINCT b.RequestKey) AS GroundedRequestCount
        FROM techscope.BridgeAIRequestTechnology b
        JOIN techscope.DimTechnology t ON t.TechnologyKey=b.TechnologyKey
        GROUP BY t.TechnologyId,t.TechnologyName
        """)
        conn.commit()

        categories = int(scalar(
            cur,
            "SELECT COUNT_BIG(DISTINCT CategoryName) FROM techscope.DimTechnology "
            "WHERE CategoryName IS NOT NULL AND LTRIM(RTRIM(CategoryName))<>''"
        ))

        companies = 0
        if object_exists(cur, "techscope.DimCompany", "U"):
            companies = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.DimCompany"))

        direct_claims = indirect_claims = 0
        if object_exists(cur, "techscope.FactTechnologyRelation", "U"):
            direct_claims = int(scalar(
                cur,
                "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation "
                "WHERE UPPER(COALESCE(EvidenceType,''))='DIRECT'"
            ))
            indirect_claims = int(scalar(
                cur,
                "SELECT COUNT_BIG(*) FROM techscope.FactTechnologyRelation "
                "WHERE UPPER(COALESCE(EvidenceType,''))='INDIRECT'"
            ))

        architecture_layers = int(scalar(
            cur,
            "SELECT COUNT_BIG(DISTINCT ArchitectureLayer) "
            "FROM techscope.PbiArchitectureMapping"
        ))

        ai_requests = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"))
        success = int(scalar(
            cur,
            "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE Status='success'"
        ))
        citation = int(scalar(
            cur,
            "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE CitationFlag=1"
        ))
        avg_latency = scalar(
            cur,
            "SELECT AVG(CONVERT(decimal(18,2),LatencyMs)) FROM techscope.FactAIRequest"
        )
        if avg_latency is None:
            avg_latency = 0

        cur.execute("""
        IF OBJECT_ID(N'techscope.PbiExecutiveSummary',N'U') IS NULL
        CREATE TABLE techscope.PbiExecutiveSummary(
            TotalTechnologies bigint NOT NULL,
            Categories bigint NOT NULL,
            Companies bigint NOT NULL,
            DirectClaims bigint NOT NULL,
            IndirectClaims bigint NOT NULL,
            ArchitectureLayers bigint NOT NULL,
            AIRequests bigint NOT NULL,
            SuccessfulRequests bigint NOT NULL,
            CitationRequests bigint NOT NULL,
            AvgLatencyMs decimal(18,2) NOT NULL
        )
        """)
        conn.commit()
        cur.execute("DELETE FROM techscope.PbiExecutiveSummary")
        cur.execute("""
        INSERT INTO techscope.PbiExecutiveSummary VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            tech_count, categories, companies, direct_claims, indirect_claims,
            architecture_layers, ai_requests, success, citation, avg_latency,
        ))
        conn.commit()

        grounded = int(scalar(cur, "SELECT COUNT_BIG(*) FROM techscope.vwPbiGroundedTechnology"))

        print(f"POWER_BI_TECHNOLOGY_ROWS={explorer_count}")
        print(f"POWER_BI_CATEGORY_COUNT={categories}")
        print(f"POWER_BI_ARCHITECTURE_MAPPING_ROWS={mapping_rows}")
        print(f"POWER_BI_AI_REQUESTS={ai_requests}")
        print(f"POWER_BI_GROUNDED_TECH_ROWS={grounded}")
        print("POWER_BI_SQL_VIEWS=PASS")
        print("POWER_BI_DEMO_ROWS=PASS")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_ai_if_needed()
    prepare_sql()
