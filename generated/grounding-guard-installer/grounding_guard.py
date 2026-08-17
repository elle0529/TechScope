from __future__ import annotations

import csv
import inspect
import json
import re
import subprocess
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from fastapi.routing import APIRoute


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/grounding-guard.json"

_SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
_SQL_DATABASE = "sqldb-techscope-dev"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _search_key() -> str:
    cfg = _config()
    service = cfg["search_service"]
    rg = cfg["resource_group"]

    candidates = [
        [
            "az", "search", "service", "query-key", "list",
            "--resource-group", rg,
            "--search-service-name", service,
            "--query", "[0].key",
            "-o", "tsv",
            "--only-show-errors",
        ],
        [
            "az", "search", "query-key", "list",
            "--resource-group", rg,
            "--service-name", service,
            "--query", "[0].key",
            "-o", "tsv",
            "--only-show-errors",
        ],
    ]

    for cmd in candidates:
        cp = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        key = (cp.stdout or "").strip()
        if cp.returncode == 0 and key:
            return key

    raise RuntimeError("GROUNDING_GUARD_SEARCH_QUERY_KEY_UNAVAILABLE")


def _search_scores(question: str) -> list[float]:
    cfg = _config()
    service = cfg["search_service"]
    index = cfg["search_index"]
    api_version = cfg["api_version"]

    url = (
        f"https://{service}.search.windows.net/"
        f"indexes/{index}/docs/search?api-version={api_version}"
    )
    body = json.dumps(
        {
            "search": question,
            "top": 5,
            "count": True,
        }
    ).encode("utf-8")

    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "api-key": _search_key(),
        },
    )

    with urlopen(req, timeout=20) as resp:
        obj = json.loads(resp.read().decode("utf-8"))

    scores = []
    for row in obj.get("value") or []:
        try:
            scores.append(float(row.get("@search.score") or 0.0))
        except Exception:
            pass
    return scores


@lru_cache(maxsize=1)
def _technology_terms() -> tuple[str, ...]:
    cfg = _config()
    generic = {
        "ai", "bi", "data", "portal", "backend", "analysis",
        "service", "services", "cloud", "api",
    }
    terms = set()

    for item in cfg.get("technology_aliases") or []:
        n = _normalize(item)
        if len(n) >= 4 and n not in generic:
            terms.add(n)

    paths = [
        ROOT / "extractor/output/technology.csv",
        ROOT / "generated/powerbi_adls_source/technology.csv",
        ROOT / "powerbi/demo_final/data/Technology.csv",
    ]

    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                headers = {h.lower(): h for h in (reader.fieldnames or [])}
                col = None
                for candidate in [
                    "technologyname", "technology_name",
                    "name", "technology",
                ]:
                    if candidate in headers:
                        col = headers[candidate]
                        break
                if not col:
                    continue
                for row in reader:
                    n = _normalize(row.get(col) or "")
                    if len(n) >= 4 and n not in generic:
                        terms.add(n)
        except Exception:
            continue

    return tuple(sorted(terms, key=len, reverse=True))


def _has_authoritative_term(question: str) -> bool:
    q = _normalize(question)
    for term in _technology_terms():
        if term in q:
            return True
    return False


def assess_grounding(question: str) -> dict[str, Any]:
    cfg = _config()
    scores = _search_scores(question)
    max_score = max(scores) if scores else 0.0
    threshold = float(cfg["threshold"])

    term_hit = _has_authoritative_term(question)
    in_domain = bool(term_hit or max_score >= threshold)

    return {
        "in_domain": in_domain,
        "max_search_score": max_score,
        "threshold": threshold,
        "authoritative_term_hit": term_hit,
        "reason": (
            "AUTHORITATIVE_TECH_TERM"
            if term_hit
            else (
                "SEARCH_SCORE_PASS"
                if in_domain
                else "SEARCH_SCORE_BELOW_DOMAIN_THRESHOLD"
            )
        ),
    }


def _extract_question(endpoint, args, kwargs) -> str:
    try:
        sig = inspect.signature(endpoint)
        bound = sig.bind_partial(*args, **kwargs)
        values = list(bound.arguments.values())
    except Exception:
        values = list(args) + list(kwargs.values())

    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()

        for attr in ("question", "query", "prompt", "text"):
            candidate = getattr(value, attr, None)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

        if isinstance(value, dict):
            for key in ("question", "query", "prompt", "text"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

    raise RuntimeError("GROUNDING_GUARD_QUESTION_EXTRACTION_FAILED")


def _request_id(payload: dict[str, Any]) -> str | None:
    for key in (
        "request_id", "requestId", "RequestId",
        "ai_request_id", "aiRequestId",
    ):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _reconcile_sql(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = _request_id(payload)
    if not request_id:
        return {
            "attempted": False,
            "reason": "REQUEST_ID_NOT_PRESENT_IN_RESPONSE",
        }

    try:
        from mssql_python import connect

        conn = connect(
            f"Server={_SQL_SERVER};"
            f"Database={_SQL_DATABASE};"
            "Authentication=ActiveDirectoryDefault;"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
        )

        try:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA='techscope'
                  AND TABLE_NAME='FactAIRequest'
                """
            )
            fact_cols = {str(r[0]) for r in cur.fetchall()}

            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA='techscope'
                  AND TABLE_NAME='BridgeAIRequestTechnology'
                """
            )
            bridge_cols = {str(r[0]) for r in cur.fetchall()}

            fact_req_col = next(
                (
                    c for c in
                    ["RequestId", "AIRequestId", "request_id"]
                    if c in fact_cols
                ),
                None,
            )
            bridge_req_col = next(
                (
                    c for c in
                    ["RequestId", "AIRequestId", "request_id"]
                    if c in bridge_cols
                ),
                None,
            )

            set_parts = []
            params: list[Any] = []

            for candidate in ["Grounded", "IsGrounded"]:
                if candidate in fact_cols:
                    set_parts.append(f"[{candidate}]=?")
                    params.append(0)
                    break

            for candidate in ["CitationCount", "CitationsCount"]:
                if candidate in fact_cols:
                    set_parts.append(f"[{candidate}]=?")
                    params.append(0)
                    break

            fact_updated = False
            bridge_deleted = False

            if fact_req_col and set_parts:
                sql = (
                    "UPDATE techscope.FactAIRequest SET "
                    + ", ".join(set_parts)
                    + f" WHERE [{fact_req_col}]=?"
                )
                cur.execute(sql, tuple(params + [request_id]))
                fact_updated = True

            if bridge_req_col:
                cur.execute(
                    f"DELETE FROM techscope.BridgeAIRequestTechnology "
                    f"WHERE [{bridge_req_col}]=?",
                    (request_id,),
                )
                bridge_deleted = True

            conn.commit()

            return {
                "attempted": True,
                "request_id": request_id,
                "fact_updated": fact_updated,
                "bridge_deleted": bridge_deleted,
            }
        finally:
            conn.close()

    except Exception as exc:
        return {
            "attempted": True,
            "request_id": request_id,
            "error": repr(exc),
        }


def _force_ungrounded(result: Any, assessment: dict[str, Any]) -> Any:
    if isinstance(result, dict):
        payload = dict(result)
    elif hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif hasattr(result, "dict"):
        payload = result.dict()
    else:
        raise RuntimeError(
            f"GROUNDING_GUARD_UNSUPPORTED_RESPONSE_TYPE={type(result)!r}"
        )

    payload["grounded"] = False

    empty_keys = [
        "citations",
        "technology_ids",
        "technologyIds",
        "grounded_technology_ids",
        "groundedTechnologyIds",
        "grounded_technologies",
        "groundedTechnologies",
    ]
    for key in empty_keys:
        payload[key] = []

    payload["answer"] = (
        "TechScope 지식베이스에서 이 질문을 뒷받침할 "
        "근거를 찾지 못했습니다."
    )
    payload["grounding_guard"] = {
        "status": "BLOCKED_OUT_OF_DOMAIN",
        **assessment,
    }
    payload["grounding_persistence_reconciliation"] = _reconcile_sql(payload)
    return payload


def install_grounding_guard(app) -> None:
    for route in app.router.routes:
        endpoint = getattr(route, "endpoint", None)
        if getattr(endpoint, "_techscope_grounding_guard_wrapped", False):
            return

    target_index = None
    target = None

    for index, route in enumerate(app.router.routes):
        if not isinstance(route, APIRoute):
            continue
        methods = set(route.methods or set())
        if route.path == "/ask" and "POST" in methods:
            target_index = index
            target = route
            break

    if target is None or target_index is None:
        raise RuntimeError("GROUNDING_GUARD_ASK_ROUTE_NOT_FOUND")

    original = target.endpoint

    @wraps(original)
    async def guarded(*args, **kwargs):
        question = _extract_question(original, args, kwargs)
        result = original(*args, **kwargs)

        if inspect.isawaitable(result):
            result = await result

        assessment = assess_grounding(question)

        if assessment["in_domain"]:
            if isinstance(result, dict):
                payload = dict(result)
                payload["grounding_guard"] = {
                    "status": "PASS_IN_DOMAIN",
                    **assessment,
                }
                return payload
            return result

        return _force_ungrounded(result, assessment)

    guarded._techscope_grounding_guard_wrapped = True

    app.router.routes.pop(target_index)

    app.add_api_route(
        target.path,
        guarded,
        methods=list(target.methods or {"POST"}),
        response_model=target.response_model,
        status_code=target.status_code,
        tags=target.tags,
        summary=target.summary,
        description=target.description,
        response_description=target.response_description,
        responses=target.responses,
        deprecated=target.deprecated,
        operation_id=target.operation_id,
        name=target.name,
    )

    new_route = app.router.routes.pop()
    app.router.routes.insert(target_index, new_route)
