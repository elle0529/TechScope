from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = "/workspaces/TechScope"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from mssql_python import connect

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def snapshot() -> tuple[int, int]:
    conn = connect(CS)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
        requests = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT_BIG(*) FROM techscope.BridgeAIRequestTechnology")
        bridge = int(cur.fetchone()[0])
        return requests, bridge
    finally:
        conn.close()


before_requests, before_bridge = snapshot()

from backend.app.main import app  # noqa: E402

client = TestClient(app)
health = client.get("/health")
print(f"HEALTH_STATUS={health.status_code}")
assert health.status_code == 200
assert health.json() == {"status": "ok"}

question = (
    "What role does Azure Databricks play in TechScope? "
    "Include authoritative technology IDs."
)
response = client.post("/ask", json={"question": question})
print(f"ASK_STATUS={response.status_code}")
assert response.status_code == 200, response.text

body = response.json()
grounded = bool(body.get("grounded"))
citations = list(body.get("citations") or [])
grounding_ids = sorted(set(body.get("grounded_technology_ids") or []))

print(f"GROUNDED={grounded}")
print(f"CITATIONS={len(citations)}")
print(f"GROUNDED_TECHNOLOGY_IDS={','.join(grounding_ids)}")

assert grounded is True
assert citations
assert grounding_ids

after_requests, after_bridge = snapshot()

assert after_requests == before_requests + 1, (before_requests, after_requests)

conn = connect(CS)
try:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TOP (1)
            r.RequestKey,
            CONVERT(varchar(36), r.RequestId),
            r.Status,
            r.RetrievedChunkCount,
            r.CitationFlag,
            r.LatencyMs,
            r.ModelName
        FROM techscope.FactAIRequest r
        ORDER BY r.RequestKey DESC
        """
    )
    row = cur.fetchone()
    assert row is not None
    request_key = int(row[0])
    request_id = str(row[1])
    status = str(row[2])
    retrieved_count = int(row[3])
    citation_flag = int(row[4])
    latency_ms = int(row[5])
    model_name = str(row[6])

    cur.execute(
        """
        SELECT t.TechnologyId
        FROM techscope.BridgeAIRequestTechnology b
        JOIN techscope.DimTechnology t
          ON t.TechnologyKey = b.TechnologyKey
        WHERE b.RequestKey = ?
        ORDER BY t.TechnologyId
        """,
        (request_key,),
    )
    persisted_ids = [str(r[0]) for r in cur.fetchall()]
finally:
    conn.close()

print(f"REQUEST_KEY={request_key}")
print(f"REQUEST_STATUS={status}")
print(f"PERSISTED_TECHNOLOGY_IDS={','.join(persisted_ids)}")
print(f"REQUESTS_BEFORE={before_requests}")
print(f"REQUESTS_AFTER={after_requests}")
print(f"BRIDGE_BEFORE={before_bridge}")
print(f"BRIDGE_AFTER={after_bridge}")

assert status == "success"
assert citation_flag == 1
assert retrieved_count == len(set(body.get("retrieved_chunk_ids") or []))
assert latency_ms >= 0
assert model_name
assert persisted_ids == grounding_ids, (persisted_ids, grounding_ids)
assert after_bridge == before_bridge + len(grounding_ids)

evidence = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "component": "CMP_FASTAPI",
    "capability": "P2C Azure SQL operations persistence",
    "status": "PASS",
    "flow": [
        "FastAPI /ask",
        "Azure AI Search",
        "Azure OpenAI",
        "AzureSqlInteractionSink",
        "FactAIRequest",
        "BridgeAIRequestTechnology",
    ],
    "health_status": health.status_code,
    "ask_status": response.status_code,
    "grounded": grounded,
    "citation_count": len(citations),
    "grounded_technology_ids": grounding_ids,
    "persisted_technology_ids": persisted_ids,
    "request_key": request_key,
    "request_id": request_id,
    "retrieved_chunk_count": retrieved_count,
    "latency_ms": latency_ms,
    "model_name": model_name,
    "requests_before": before_requests,
    "requests_after": after_requests,
    "bridge_before": before_bridge,
    "bridge_after": after_bridge,
    "secrets_persisted": False,
}

evidence_path = Path(
    "/workspaces/TechScope/evidence/backend/p2c-sql-persistence.json"
)
evidence_path.parent.mkdir(parents=True, exist_ok=True)
evidence_path.write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

summary_path = Path(
    "/workspaces/TechScope/results/latest/p2c-summary.json"
)
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(
    json.dumps(
        {
            "timestamp": evidence["timestamp"],
            "status": "PASS",
            "capability": evidence["capability"],
            "request_key": request_key,
            "grounded_technology_ids": grounding_ids,
            "secrets_persisted": False,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

print("GROUNDING_BRIDGE_EQUALITY=PASS")
print("P2C_FASTAPI_SQL_LIVE_E2E=PASS")
print("SECRETS_WRITTEN_TO_REPO=NO")
