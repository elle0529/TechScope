from __future__ import annotations

from pathlib import Path

MAIN = Path("/workspaces/TechScope/backend/app/main.py")
LIVE = Path("/workspaces/TechScope/backend/demo/live.html")

text = MAIN.read_text(encoding="utf-8")

import_line = "from backend.demo.powerbi_sync import sync_powerbi_snapshot\n"
if import_line not in text:
    marker = "from backend.demo.status import get_demo_status\n"
    if marker not in text:
        raise RuntimeError("demo status import not found")
    text = text.replace(marker, marker + import_line, 1)

route = (
    '    @app.post("/demo/powerbi-sync", include_in_schema=False)\n'
    '    def demo_powerbi_sync() -> dict:\n'
    '        return sync_powerbi_snapshot()\n\n'
)
if 'def demo_powerbi_sync() -> dict:' not in text:
    marker = '    @app.get("/health")\n'
    if marker not in text:
        raise RuntimeError("/health marker not found")
    text = text.replace(marker, route + marker, 1)

MAIN.write_text(text, encoding="utf-8")

html = LIVE.read_text(encoding="utf-8")

old_proof = (
    '<div><span>SQL Persisted</span><b id="sqlPersisted">-</b></div>\n'
    '      </div>'
)
new_proof = (
    '<div><span>SQL Persisted</span><b id="sqlPersisted">-</b></div>\n'
    '        <div><span>Power BI Snapshot</span><b id="powerbiSync">-</b></div>\n'
    '      </div>'
)
if 'id="powerbiSync"' not in html:
    if old_proof not in html:
        raise RuntimeError("Operational proof block not found")
    html = html.replace(old_proof, new_proof, 1)

old = '''    const after = await getStatus();
    document.getElementById("resultArea").classList.remove("hidden");'''
new = '''    const syncResponse = await fetch("/demo/powerbi-sync", {
      method:"POST",
      cache:"no-store"
    });
    const syncBody = await syncResponse.json();
    if(!syncResponse.ok || syncBody.status !== "PASS"){
      throw new Error("Power BI snapshot sync failed: " + JSON.stringify(syncBody));
    }

    const after = await getStatus();
    document.getElementById("resultArea").classList.remove("hidden");'''

if 'const syncResponse = await fetch("/demo/powerbi-sync"' not in html:
    if old not in html:
        raise RuntimeError("Live UI post-ask status marker not found")
    html = html.replace(old, new, 1)

old2 = '''    const persisted = after.ai_request_count === beforeCount + 1;
    document.getElementById("sqlPersisted").textContent = persisted ? "PASS" : "CHECK";'''
new2 = '''    const persisted = after.ai_request_count === beforeCount + 1;
    const synced = syncBody.ai_request_count === after.ai_request_count;
    document.getElementById("powerbiSync").textContent = synced ? "PASS" : "CHECK";
    document.getElementById("powerbiSync").className = synced ? "pass" : "fail";
    document.getElementById("sqlPersisted").textContent = persisted ? "PASS" : "CHECK";'''

if 'const synced = syncBody.ai_request_count' not in html:
    if old2 not in html:
        raise RuntimeError("Persistence marker not found")
    html = html.replace(old2, new2, 1)

LIVE.write_text(html, encoding="utf-8")
print("LIVE_UI_POWERBI_SYNC_PATCH=PASS")
