from __future__ import annotations

from pathlib import Path

path = Path("/workspaces/TechScope/backend/app/main.py")
text = path.read_text(encoding="utf-8")

if "from fastapi.responses import FileResponse" not in text:
    text = text.replace(
        "from fastapi import FastAPI, HTTPException",
        "from fastapi import FastAPI, HTTPException\nfrom fastapi.responses import FileResponse",
        1,
    )

marker = '    @app.get("/health")\n'
if marker not in text:
    raise RuntimeError("main.py health marker not found")

route = (
    '    @app.get("/", include_in_schema=False)\n'
    '    def demo_page() -> FileResponse:\n'
    '        return FileResponse("/workspaces/TechScope/backend/demo/index.html")\n\n'
)

if "def demo_page()" not in text:
    text = text.replace(marker, route + marker, 1)

path.write_text(text, encoding="utf-8")
print("FINAL_AI_DEMO_ROUTE=PASS")
