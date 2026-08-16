from __future__ import annotations

from pathlib import Path

MAIN = Path("/workspaces/TechScope/backend/app/main.py")
text = MAIN.read_text(encoding="utf-8")

if "from fastapi.responses import FileResponse" not in text:
    text = text.replace(
        "from fastapi import FastAPI, HTTPException",
        "from fastapi import FastAPI, HTTPException\nfrom fastapi.responses import FileResponse",
        1,
    )

if "from backend.demo.status import get_demo_status" not in text:
    # Put project import near other imports without depending on exact local layout.
    marker = "from fastapi.responses import FileResponse\n"
    if marker in text:
        text = text.replace(
            marker,
            marker + "from backend.demo.status import get_demo_status\n",
            1,
        )
    else:
        # Fallback after the last top-level import block is not safe; fail instead.
        raise RuntimeError("Could not insert demo status import safely")

# Replace old demo page body if an earlier demo route exists.
old = (
    '    @app.get("/", include_in_schema=False)\n'
    '    def demo_page() -> FileResponse:\n'
    '        return FileResponse("/workspaces/TechScope/backend/demo/index.html")\n'
)
new = (
    '    @app.get("/", include_in_schema=False)\n'
    '    def demo_page() -> FileResponse:\n'
    '        return FileResponse("/workspaces/TechScope/backend/demo/live.html")\n'
)
if old in text:
    text = text.replace(old, new, 1)

# If no root demo route exists, insert it before /health.
if 'def demo_page() -> FileResponse:' not in text:
    marker = '    @app.get("/health")\n'
    if marker not in text:
        raise RuntimeError("Could not find /health route insertion point")
    text = text.replace(marker, new + "\n" + marker, 1)

status_route = (
    '    @app.get("/demo/status", include_in_schema=False)\n'
    '    def demo_status() -> dict:\n'
    '        return get_demo_status()\n\n'
)
if 'def demo_status() -> dict:' not in text:
    marker = '    @app.get("/health")\n'
    if marker not in text:
        raise RuntimeError("Could not find /health route for status insertion")
    text = text.replace(marker, status_route + marker, 1)

MAIN.write_text(text, encoding="utf-8")
print("LIVE_UI_BACKEND_PATCH=PASS")
