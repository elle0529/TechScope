#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
REPORT = ROOT / "results/latest/p3-preflight-v3.json"


def parse_routes(path: Path):
    routes = []
    if not path.exists():
        return routes
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return routes

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            fn = deco.func
            if not isinstance(fn, ast.Attribute):
                continue
            if fn.attr not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not deco.args:
                continue
            arg = deco.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                routes.append({
                    "method": fn.attr.upper(),
                    "path": arg.value,
                    "function": node.name,
                })
    return routes


def collect_hits():
    keywords = [
        "cosmos",
        "feedback",
        "session",
        "conversation",
        "FactAIRequest",
        "BridgeAIRequestTechnology",
        "CMP_COSMOS",
        "CMP_TEAMS",
    ]
    allowed = {".py", ".toml", ".json", ".md", ".yml", ".yaml", ".txt"}
    hits = []

    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in allowed:
            continue
        if any(x in p.parts for x in [".git", ".venv", "node_modules", "__pycache__"]):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = text.lower()
        matched = [k for k in keywords if k.lower() in low]
        if matched:
            hits.append({
                "path": str(p.relative_to(ROOT)),
                "keywords": matched,
            })
    return hits


def dependency_state():
    texts = []
    for rel in [
        "pyproject.toml",
        "requirements.txt",
        "backend/requirements.txt",
    ]:
        p = ROOT / rel
        if p.exists():
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))

    blob = "\n".join(texts).lower()
    return {
        "azure-cosmos": "azure-cosmos" in blob,
        "azure-identity": "azure-identity" in blob,
        "fastapi": "fastapi" in blob,
        "pydantic": "pydantic" in blob,
    }


def env_names():
    names = set()
    patterns = [
        re.compile(r'["\']((?:AZURE_)?COSMOS[A-Z0-9_]+)["\']'),
        re.compile(r'["\'](TECHSCOPE_[A-Z0-9_]*(?:COSMOS|SESSION|FEEDBACK)[A-Z0-9_]*)["\']'),
    ]
    for p in (ROOT / "backend").rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            names.update(pat.findall(text))
    return sorted(names)


def main():
    print("P3_PREFLIGHT_V3=START", flush=True)

    main_py = ROOT / "backend/app/main.py"
    routes = parse_routes(main_py)
    hits = collect_hits()
    deps = dependency_state()
    envs = env_names()

    cosmos_files = sorted({
        h["path"] for h in hits
        if any(k.lower() == "cosmos" for k in h["keywords"])
    })
    feedback_files = sorted({
        h["path"] for h in hits
        if any(k.lower() == "feedback" for k in h["keywords"])
    })
    session_files = sorted({
        h["path"] for h in hits
        if any(k.lower() in {"session", "conversation"} for k in h["keywords"])
    })

    print(f"P3_ROUTES={len(routes)}", flush=True)
    for r in routes:
        print(f"P3_ROUTE={r['method']} {r['path']} -> {r['function']}", flush=True)

    print(f"P3_DEP_AZURE_COSMOS={'YES' if deps['azure-cosmos'] else 'NO'}", flush=True)
    print(f"P3_DEP_AZURE_IDENTITY={'YES' if deps['azure-identity'] else 'NO'}", flush=True)

    print(f"P3_COSMOS_FILES={len(cosmos_files)}", flush=True)
    for x in cosmos_files[:20]:
        print(f"P3_COSMOS_FILE={x}", flush=True)

    print(f"P3_FEEDBACK_FILES={len(feedback_files)}", flush=True)
    for x in feedback_files[:20]:
        print(f"P3_FEEDBACK_FILE={x}", flush=True)

    print(f"P3_SESSION_FILES={len(session_files)}", flush=True)
    for x in session_files[:20]:
        print(f"P3_SESSION_FILE={x}", flush=True)

    print(f"P3_ENV_NAME_COUNT={len(envs)}", flush=True)
    for x in envs:
        print(f"P3_ENV_NAME={x}", flush=True)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "routes": routes,
        "dependencies": deps,
        "cosmos_files": cosmos_files,
        "feedback_files": feedback_files,
        "session_files": session_files,
        "env_names": envs,
        "keyword_hits": hits,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("P3_PREFLIGHT_V3=PASS", flush=True)
    print("REPORT=results/latest/p3-preflight-v3.json", flush=True)
    print("NEXT_ACTION=SEND_CONSOLE_OUTPUT_FOR_P3_IMPLEMENTATION", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
