#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
REPORT = ROOT / "results/latest/p3-checkpoint-preflight.json"

SENSITIVE_NAMES = {
    ".env",
    ".databrickscfg",
}
SENSITIVE_PARTS = {
    ".azure",
    "__pycache__",
    ".venv",
    "node_modules",
}


def run(cmd, *, check=True, timeout=120):
    cp = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + (cp.stdout or "")[-5000:]
            + "\nSTDERR:\n"
            + (cp.stderr or "")[-5000:]
        )
    return cp


def git(*args, check=True, timeout=120):
    return run(["git", *args], check=check, timeout=timeout)


def gh_user():
    cp = run(
        ["gh", "api", "user", "--jq", '[.login, (.id|tostring)] | @tsv'],
        check=False,
        timeout=60,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "GITHUB_AUTH=FAIL\n"
            + (cp.stderr or "")[-2000:]
        )
    parts = (cp.stdout or "").strip().split("\t")
    if len(parts) != 2:
        raise RuntimeError("GITHUB_USER_RESPONSE_INVALID")
    return parts[0], parts[1]


def verify_remote():
    remote = (git("remote", "get-url", "origin").stdout or "").strip()
    expected = "https://github.com/elle0529/TechScope.git"
    if remote != expected:
        raise RuntimeError(
            f"GIT_REMOTE_MISMATCH expected={expected} actual={remote}"
        )
    return remote


def staged_paths():
    cp = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [
        x.strip()
        for x in (cp.stdout or "").splitlines()
        if x.strip()
    ]


def safety_check(paths):
    bad = []
    for p in paths:
        pp = Path(p)
        if pp.name in SENSITIVE_NAMES and pp.name != ".env.example":
            bad.append(p)
            continue
        parts = set(pp.parts)
        if parts & SENSITIVE_PARTS:
            bad.append(p)
    if bad:
        raise RuntimeError(
            "GIT_SAFETY_SCAN=FAIL forbidden_paths="
            + ",".join(bad[:20])
        )

    # Review staged text diff for likely literal secrets.
    cp = git("diff", "--cached", "--unified=0", check=False)
    diff = cp.stdout or ""

    patterns = [
        r'(?i)password\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)api[_-]?key\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)account[_-]?key\s*=\s*["\'][^"\']{16,}["\']',
        r'(?i)client[_-]?secret\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{20,}',
    ]
    for pat in patterns:
        if re.search(pat, diff):
            raise RuntimeError(
                "GIT_SAFETY_SCAN=FAIL possible_literal_secret_in_staged_diff"
            )


def checkpoint():
    print("GIT_CHECKPOINT=START", flush=True)

    remote = verify_remote()
    print(f"GIT_REMOTE=PASS {remote}", flush=True)

    login, uid = gh_user()
    if login != "elle0529":
        raise RuntimeError(
            f"GITHUB_AUTH_USER_MISMATCH expected=elle0529 actual={login}"
        )

    email = f"{uid}+{login}@users.noreply.github.com"
    git("config", "--local", "user.name", login)
    git("config", "--local", "user.email", email)
    print(f"GIT_IDENTITY=PASS USER={login}", flush=True)

    git("add", "-A")
    paths = staged_paths()
    safety_check(paths)
    print(f"GIT_SAFETY_SCAN=PASS STAGED_FILES={len(paths)}", flush=True)

    if paths:
        git(
            "commit",
            "-m",
            "Complete P1E technology relation pipeline",
            timeout=120,
        )
        print("GIT_COMMIT=PASS", flush=True)
    else:
        print("GIT_COMMIT=NO_CHANGES", flush=True)

    local_sha = (git("rev-parse", "HEAD").stdout or "").strip()
    print(f"LOCAL_MAIN_SHA={local_sha}", flush=True)

    cp = git("push", "origin", "main", timeout=180)
    print("GIT_PUSH=PASS", flush=True)

    remote_sha = (
        git("ls-remote", "origin", "refs/heads/main").stdout or ""
    ).strip().split()
    if not remote_sha:
        raise RuntimeError("REMOTE_MAIN_SHA_NOT_FOUND")
    remote_sha = remote_sha[0]

    print(f"REMOTE_MAIN_SHA={remote_sha}", flush=True)

    if remote_sha != local_sha:
        raise RuntimeError(
            f"REMOTE_VERIFY=FAIL local={local_sha} remote={remote_sha}"
        )

    print("REMOTE_VERIFY=PASS", flush=True)

    return {
        "remote": remote,
        "github_user": login,
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "staged_files": len(paths),
    }


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
            if fn.attr not in {
                "get", "post", "put", "patch", "delete", "options"
            }:
                continue
            if not deco.args:
                continue
            arg = deco.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                routes.append(
                    {
                        "method": fn.attr.upper(),
                        "path": arg.value,
                        "function": node.name,
                    }
                )
    return routes


def text_env_names(paths):
    names = set()
    pattern = re.compile(
        r'\b(?:os\.environ|getenv|os\.getenv)\s*'
        r'(?:\[|\()\s*["\']([A-Z][A-Z0-9_]{2,})["\']'
    )
    simpler = re.compile(
        r'["\']((?:AZURE_)?COSMOS[A-Z0-9_]*|'
        r'COSMOS_[A-Z0-9_]+|'
        r'TECHSCOPE_[A-Z0-9_]*(?:COSMOS|SESSION|FEEDBACK)[A-Z0-9_]*)["\']'
    )

    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        names.update(pattern.findall(text))
        names.update(simpler.findall(text))
    return sorted(names)


def grep_files(keywords):
    hits = []
    allowed = {".py", ".toml", ".json", ".md", ".yml", ".yaml", ".txt"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in allowed:
            continue
        if any(part in {".git", ".venv", "node_modules"} for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = text.lower()
        matched = [k for k in keywords if k.lower() in low]
        if matched:
            hits.append(
                {
                    "path": str(p.relative_to(ROOT)),
                    "keywords": matched,
                }
            )
    return hits[:120]


def dependency_state():
    texts = []
    for rel in ["pyproject.toml", "requirements.txt", "backend/requirements.txt"]:
        p = ROOT / rel
        if p.exists():
            try:
                texts.append((rel, p.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                pass

    found = {}
    for name in [
        "azure-cosmos",
        "azure-identity",
        "fastapi",
        "pydantic",
    ]:
        found[name] = any(name.lower() in t.lower() for _, t in texts)
    return found


def preflight():
    print("P3_PREFLIGHT=START", flush=True)

    backend = ROOT / "backend/app"
    main_py = backend / "main.py"

    routes = parse_routes(main_py)
    env_names = text_env_names(
        list(backend.rglob("*.py"))
        + [ROOT / "pyproject.toml", ROOT / ".env.example"]
    )
    hits = grep_files(
        [
            "cosmos",
            "feedback",
            "session",
            "conversation",
            "FactAIRequest",
            "BridgeAIRequestTechnology",
            "CMP_COSMOS",
            "CMP_TEAMS",
        ]
    )
    deps = dependency_state()

    backend_files = sorted(
        str(p.relative_to(ROOT))
        for p in backend.glob("*.py")
        if p.is_file()
    )

    cosmos_files = [
        x["path"]
        for x in hits
        if "cosmos" in [k.lower() for k in x["keywords"]]
    ]
    feedback_files = [
        x["path"]
        for x in hits
        if "feedback" in [k.lower() for k in x["keywords"]]
    ]
    session_files = [
        x["path"]
        for x in hits
        if any(
            k.lower() in {"session", "conversation"}
            for k in x["keywords"]
        )
    ]

    print(f"P3_BACKEND_PY_FILES={len(backend_files)}", flush=True)
    print(f"P3_ROUTES={len(routes)}", flush=True)
    for r in routes:
        print(
            f"P3_ROUTE={r['method']} {r['path']} -> {r['function']}",
            flush=True,
        )

    print(
        f"P3_DEP_AZURE_COSMOS={'YES' if deps['azure-cosmos'] else 'NO'}",
        flush=True,
    )
    print(
        f"P3_DEP_AZURE_IDENTITY={'YES' if deps['azure-identity'] else 'NO'}",
        flush=True,
    )

    print(f"P3_COSMOS_FILES={len(set(cosmos_files))}", flush=True)
    for x in sorted(set(cosmos_files))[:20]:
        print(f"P3_COSMOS_FILE={x}", flush=True)

    print(f"P3_FEEDBACK_FILES={len(set(feedback_files))}", flush=True)
    for x in sorted(set(feedback_files))[:20]:
        print(f"P3_FEEDBACK_FILE={x}", flush=True)

    print(f"P3_SESSION_FILES={len(set(session_files))}", flush=True)
    for x in sorted(set(session_files))[:20]:
        print(f"P3_SESSION_FILE={x}", flush=True)

    print(f"P3_ENV_NAME_COUNT={len(env_names)}", flush=True)
    for name in env_names:
        if any(k in name for k in ["COSMOS", "SESSION", "FEEDBACK"]):
            print(f"P3_ENV_NAME={name}", flush=True)

    report = {
        "checkpoint": None,
        "backend_files": backend_files,
        "routes": routes,
        "dependencies": deps,
        "env_names": env_names,
        "keyword_hits": hits,
        "cosmos_files": sorted(set(cosmos_files)),
        "feedback_files": sorted(set(feedback_files)),
        "session_files": sorted(set(session_files)),
    }
    return report


def main():
    print("TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_V1=START", flush=True)

    checkpoint_info = checkpoint()
    report = preflight()
    report["checkpoint"] = checkpoint_info

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("P3_PREFLIGHT=PASS", flush=True)
    print(
        "REPORT=results/latest/p3-checkpoint-preflight.json",
        flush=True,
    )
    print("NEXT_ACTION=SEND_CONSOLE_OUTPUT_FOR_P3_IMPLEMENTATION", flush=True)
    print("TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_V1=PASS", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(
            f"TECHSCOPE_P3_CHECKPOINT_PREFLIGHT_V1=FAIL "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        raise
