from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from mssql_python import connect

from backend.app.main import app

REPO = Path("/workspaces/TechScope")
OUT_HTML = REPO / "results" / "latest" / "final-ai-demo.html"
OUT_JSON = REPO / "results" / "latest" / "final-ai-demo.json"

QUESTION = (
    "What role does Azure Databricks play in TechScope? "
    "Include authoritative technology IDs."
)

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def request_count() -> int:
    conn = connect(CS)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


before = request_count()

client = TestClient(app)

health = client.get("/health")
if health.status_code != 200 or health.json().get("status") != "ok":
    raise RuntimeError(f"Health failed: {health.status_code} {health.text}")

print("FINAL_AI_DEMO_HEALTH=PASS")
print("FINAL_AI_DEMO_ASK=START")

response = client.post("/ask", json={"question": QUESTION})
if response.status_code != 200:
    raise RuntimeError(
        f"/ask failed: {response.status_code} {response.text}"
    )

body = response.json()
grounded = bool(body.get("grounded"))
citations = list(body.get("citations") or [])
tech_ids = sorted(set(body.get("grounded_technology_ids") or []))
retrieved = list(body.get("retrieved_chunk_ids") or [])
answer = str(body.get("answer") or "")

if not grounded:
    raise RuntimeError("Live response was not grounded")
if not citations:
    raise RuntimeError("Live response returned no citations")
if not tech_ids:
    raise RuntimeError("Live response returned no grounded technology IDs")
if not answer.strip():
    raise RuntimeError("Live response answer is empty")

after = request_count()
if after != before + 1:
    raise RuntimeError(
        f"SQL persistence count mismatch: before={before}, after={after}"
    )

generated_at = datetime.now(timezone.utc).isoformat()

rows = []
for c in citations:
    rows.append(
        "<tr>"
        f"<td>{html.escape(str(c.get('chunk_id') or ''))}</td>"
        f"<td>{html.escape(str(c.get('source_id') or ''))}</td>"
        f"<td>{html.escape(', '.join(c.get('technology_ids') or []))}</td>"
        f"<td>{html.escape(', '.join(c.get('category') or []))}</td>"
        "</tr>"
    )

tech_html = " ".join(
    f'<span class="badge">{html.escape(str(t))}</span>'
    for t in tech_ids
)

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TechScope Final AI Demo</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f7fa;color:#1f1f1f}}
.wrap{{max-width:1120px;margin:32px auto;padding:0 24px}}
.hero{{background:linear-gradient(135deg,#0f6cbd,#115ea3);color:#fff;padding:26px;border-radius:14px}}
.hero h1{{margin:0 0 7px;font-size:31px}}
.hero p{{margin:0;opacity:.9}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}}
.kpi,.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:17px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
.kpi b{{display:block;font-size:27px;margin-top:7px}}
.card{{margin-top:16px}}
.answer{{white-space:pre-wrap;line-height:1.6}}
.badge{{display:inline-block;background:#e8f2fc;color:#0f548c;padding:7px 10px;border-radius:999px;margin:3px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:9px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}
.pass{{color:#107c10;font-weight:700}}
.meta{{font-size:12px;color:#666;margin-top:12px}}
.question{{font-size:17px;font-weight:600}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>TechScope — Final AI Knowledge Ops Demo</h1>
    <p>Azure AI Search → Azure OpenAI → FastAPI → Azure SQL operational persistence</p>
  </div>

  <div class="grid">
    <div class="kpi">API Health<b class="pass">PASS</b></div>
    <div class="kpi">Grounded<b class="pass">{str(grounded)}</b></div>
    <div class="kpi">Citations<b>{len(citations)}</b></div>
    <div class="kpi">SQL Requests<b>{after}</b></div>
  </div>

  <div class="card">
    <h3>Question</h3>
    <div class="question">{html.escape(QUESTION)}</div>
  </div>

  <div class="card">
    <h3>Grounded Answer</h3>
    <div class="answer">{html.escape(answer)}</div>
  </div>

  <div class="card">
    <h3>Authoritative Technology IDs</h3>
    <div>{tech_html}</div>
  </div>

  <div class="card">
    <h3>Citations</h3>
    <table>
      <thead>
        <tr>
          <th>Chunk ID</th>
          <th>Source</th>
          <th>Technology IDs</th>
          <th>Category</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>

  <div class="card">
    <h3>Operational Proof</h3>
    <p>FactAIRequest count: <b>{before} → {after}</b></p>
    <p>Retrieved chunks: <b>{len(retrieved)}</b></p>
    <p>Grounded technology IDs: <b>{len(tech_ids)}</b></p>
    <p class="pass">LIVE_RAG_AND_SQL_PERSISTENCE = PASS</p>
    <div class="meta">Generated from the live TechScope runtime at {html.escape(generated_at)}</div>
  </div>
</div>
</body>
</html>
"""

OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
OUT_HTML.write_text(page, encoding="utf-8")

evidence = {
    "timestamp": generated_at,
    "status": "PASS",
    "question": QUESTION,
    "health_status": health.status_code,
    "ask_status": response.status_code,
    "grounded": grounded,
    "citation_count": len(citations),
    "grounded_technology_ids": tech_ids,
    "retrieved_chunk_count": len(retrieved),
    "sql_request_count_before": before,
    "sql_request_count_after": after,
    "html": str(OUT_HTML),
    "secrets_persisted": False,
}
OUT_JSON.write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print("FINAL_AI_DEMO_ASK=PASS")
print(f"FINAL_AI_DEMO_GROUNDED={grounded}")
print(f"FINAL_AI_DEMO_CITATIONS={len(citations)}")
print(f"FINAL_AI_DEMO_TECHNOLOGY_IDS={len(tech_ids)}")
print(f"FINAL_AI_DEMO_SQL_BEFORE={before}")
print(f"FINAL_AI_DEMO_SQL_AFTER={after}")
print("FINAL_AI_DEMO_SQL_PERSISTENCE=PASS")
print(f"FINAL_AI_DEMO_HTML={OUT_HTML}")
print("FINAL_AI_DEMO_CAPTURE=PASS")
print("SECRETS_WRITTEN_TO_REPO=NO")
