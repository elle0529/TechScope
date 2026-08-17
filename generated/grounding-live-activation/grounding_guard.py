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

    req = Request(
        url,
        data=json.dumps(
            {
                "search": question,
                "top": 5,
                "count": True,
            }
        ).encode("utf-8"),
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
        "ai", "bi", "data", "portal", "backend",
        "analysis", "service", "services", "cloud", "api",
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
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                reader = csv.DictReader(f)
                headers = {
                    h.lower(): h
                    for h in (reader.fieldnames or [])
                }

                col = None
                for candidate in [
                    "technologyname",
                    "technology_name",
                    "name",
                    "technology",
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

    return tuple(
        sorted(
            terms,
            key=len,
            reverse=True,
        )
    )


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

    raise RuntimeError(
        "GROUNDING_GUARD_QUESTION_EXTRACTION_FAILED"
    )


def _sql_connect():
    from mssql_python import connect

    return connect(
        f"Server={_SQL_SERVER};"
        f"Database={_SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )


def _max_request_key() -> int | None:
    try:
        conn = _sql_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(MAX(RequestKey), 0)
                FROM techscope.FactAIRequest
                """
            )
            return int(cur.fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return None


def _reconcile_new_out_of_domain_rows(
    before_request_key: int | None,
) -> dict[str, Any]:
    if before_request_key is None:
        return {
            "attempted": False,
            "reason": "REQUEST_KEY_BASELINE_UNAVAILABLE",
        }

    try:
        conn = _sql_connect()

        try:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT RequestKey
                FROM techscope.FactAIRequest
                WHERE RequestKey > ?
                ORDER BY RequestKey
                """,
                (before_request_key,),
            )
            keys = [
                int(row[0])
                for row in cur.fetchall()
            ]

            if not keys:
                return {
                    "attempted": True,
                    "rows_found": 0,
                    "fact_updated": 0,
                    "bridge_deleted": 0,
                }

            fact_updated = 0
            bridge_deleted = 0

            for request_key in keys:
                cur.execute(
                    """
                    UPDATE techscope.FactAIRequest
                    SET CitationFlag = 0
                    WHERE RequestKey = ?
                    """,
                    (request_key,),
                )
                fact_updated += 1

                cur.execute(
                    """
                    DELETE FROM techscope.BridgeAIRequestTechnology
                    WHERE RequestKey = ?
                    """,
                    (request_key,),
                )
                bridge_deleted += 1

            conn.commit()

            return {
                "attempted": True,
                "rows_found": len(keys),
                "request_keys": keys,
                "fact_updated": fact_updated,
                "bridge_delete_statements": bridge_deleted,
            }

        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    except Exception as exc:
        return {
            "attempted": True,
            "error": repr(exc),
        }


def _force_ungrounded(
    result: Any,
    assessment: dict[str, Any],
    reconciliation: dict[str, Any],
) -> Any:
    if isinstance(result, dict):
        payload = dict(result)
    elif hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif hasattr(result, "dict"):
        payload = result.dict()
    else:
        raise RuntimeError(
            "GROUNDING_GUARD_UNSUPPORTED_RESPONSE_TYPE="
            + repr(type(result))
        )

    payload["grounded"] = False

    for key in [
        "citations",
        "technology_ids",
        "technologyIds",
        "grounded_technology_ids",
        "groundedTechnologyIds",
        "grounded_technologies",
        "groundedTechnologies",
    ]:
        payload[key] = []

    payload["answer"] = (
        "TechScope 지식베이스에서 이 질문을 뒷받침할 "
        "근거를 찾지 못했습니다."
    )

    # Diagnostic metadata. FastAPI AskResponse intentionally filters this
    # from the public response because it is not a declared response field.
    payload["grounding_guard"] = {
        "status": "BLOCKED_OUT_OF_DOMAIN",
        **assessment,
    }
    payload["grounding_persistence_reconciliation"] = reconciliation

    return payload


def install_grounding_guard(app) -> None:
    for route in app.router.routes:
        endpoint = getattr(route, "endpoint", None)

        if getattr(
            endpoint,
            "_techscope_grounding_guard_wrapped",
            False,
        ):
            return

    target_index = None
    target = None

    for index, route in enumerate(app.router.routes):
        if not isinstance(route, APIRoute):
            continue

        methods = set(route.methods or set())

        if (
            route.path == "/ask"
            and "POST" in methods
        ):
            target_index = index
            target = route
            break

    if target is None or target_index is None:
        raise RuntimeError(
            "GROUNDING_GUARD_ASK_ROUTE_NOT_FOUND"
        )

    original = target.endpoint

    @wraps(original)
    async def guarded(*args, **kwargs):
        question = _extract_question(
            original,
            args,
            kwargs,
        )

        # Classify before the original /ask body runs so that a baseline
        # RequestKey can be captured for deterministic post-persistence
        # reconciliation.
        assessment = assess_grounding(question)

        before_request_key = (
            _max_request_key()
            if not assessment["in_domain"]
            else None
        )

        result = original(*args, **kwargs)

        if inspect.isawaitable(result):
            result = await result

        if assessment["in_domain"]:
            return result

        reconciliation = (
            _reconcile_new_out_of_domain_rows(
                before_request_key
            )
        )

        return _force_ungrounded(
            result,
            assessment,
            reconciliation,
        )

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
    app.router.routes.insert(
        target_index,
        new_route,
    )
