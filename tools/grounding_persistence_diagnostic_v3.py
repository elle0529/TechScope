#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
BASELINE = ROOT / "results/latest/main-final-verification.json"
GUARD_REPORT = ROOT / "results/latest/grounding-persistence-diagnostic-v3.json"
GUARD_CONFIG = ROOT / "config/grounding-guard.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

REQUIRED_ENV = {
    "TECHSCOPE_SEARCH_ENDPOINT",
    "TECHSCOPE_SEARCH_INDEX",
    "TECHSCOPE_AZURE_OPENAI_ENDPOINT",
    "TECHSCOPE_GENERATION_DEPLOYMENT",
    "TECHSCOPE_EMBEDDING_DEPLOYMENT",
}


def sql_connect():
    from mssql_python import connect

    return connect(
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )


def live_env():
    candidates = []

    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (
                (p / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="ignore")
            )
        except Exception:
            continue

        low = cmd.lower()
        if "8011" in low:
            continue
        if "uvicorn" not in low and "backend.app.main" not in low:
            continue

        try:
            raw = (p / "environ").read_bytes()
        except Exception:
            continue

        env = {}
        for chunk in raw.split(b"\0"):
            if b"=" not in chunk:
                continue
            k, v = chunk.split(b"=", 1)
            key = k.decode("utf-8", errors="ignore")
            if key.startswith("TECHSCOPE_"):
                env[key] = v.decode("utf-8", errors="ignore")

        score = len(REQUIRED_ENV & set(env))
        if score:
            candidates.append((score, int(p.name), env, cmd))

    if not candidates:
        raise RuntimeError("LIVE_FASTAPI_ENV_NOT_FOUND")

    candidates.sort(reverse=True, key=lambda x: (x[0], -x[1]))
    score, pid, env, cmd = candidates[0]

    missing = sorted(REQUIRED_ENV - set(env))
    if missing:
        raise RuntimeError(
            "LIVE_FASTAPI_ENV_INCOMPLETE=" + ",".join(missing)
        )

    print(f"LIVE_FASTAPI_PID={pid}", flush=True)
    print(f"LIVE_FASTAPI_PID_IS_1={'YES' if pid == 1 else 'NO'}", flush=True)
    print(
        f"LIVE_FASTAPI_AUTO_RELOAD={'YES' if '--reload' in cmd else 'NO'}",
        flush=True,
    )
    print(f"LIVE_TECHSCOPE_ENV_COUNT={len(env)}", flush=True)
    print("LIVE_ENV_VALUES_PRINTED=NO", flush=True)
    print("LIVE_ENV_VALUES_PERSISTED=NO", flush=True)

    return env, pid, cmd


def baseline_count():
    if not BASELINE.exists():
        return None
    try:
        obj = json.loads(BASELINE.read_text(encoding="utf-8"))
        return int(((obj.get("sql") or {}).get("ai_request")))
    except Exception:
        return None


def fact_schema(cur):
    cur.execute(
        """
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            COLUMNPROPERTY(
                OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
                c.COLUMN_NAME,
                'IsIdentity'
            ) AS IsIdentity
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA='techscope'
          AND c.TABLE_NAME='FactAIRequest'
        ORDER BY c.ORDINAL_POSITION
        """
    )
    return [
        {
            "name": str(r[0]),
            "type": str(r[1]),
            "identity": bool(r[2]),
        }
        for r in cur.fetchall()
    ]


def bridge_schema(cur):
    cur.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='techscope'
          AND TABLE_NAME='BridgeAIRequestTechnology'
        ORDER BY ORDINAL_POSITION
        """
    )
    return [
        {"name": str(r[0]), "type": str(r[1])}
        for r in cur.fetchall()
    ]


def pick(names, candidates):
    low = {n.lower(): n for n in names}
    for candidate in candidates:
        if candidate.lower() in low:
            return low[candidate.lower()]
    return None


def persistence_diagnostic():
    baseline = baseline_count()

    conn = sql_connect()
    try:
        cur = conn.cursor()
        fschema = fact_schema(cur)
        bschema = bridge_schema(cur)

        fnames = [x["name"] for x in fschema]
        bnames = [x["name"] for x in bschema]

        req_col = pick(
            fnames,
            ["RequestId", "AIRequestId", "request_id", "Id"],
        )
        grounded_col = pick(
            fnames,
            ["Grounded", "IsGrounded", "grounded"],
        )
        citation_col = pick(
            fnames,
            ["CitationCount", "CitationsCount", "citation_count"],
        )
        success_col = pick(
            fnames,
            ["Success", "IsSuccess", "success"],
        )
        created_col = pick(
            fnames,
            [
                "CreatedAtUtc", "CreatedAt", "TimestampUtc",
                "RequestTimestamp", "RequestedAt", "EventTimeUtc",
            ],
        )

        identity_col = next(
            (x["name"] for x in fschema if x["identity"]),
            None,
        )

        order_col = identity_col or created_col or req_col
        if not order_col:
            raise RuntimeError(
                "FACT_AI_REQUEST_ORDER_COLUMN_NOT_FOUND"
            )

        selected = [
            x for x in [
                req_col,
                grounded_col,
                citation_col,
                success_col,
                created_col,
                identity_col,
            ]
            if x
        ]
        # de-duplicate preserving order
        selected = list(dict.fromkeys(selected))

        sql = (
            "SELECT TOP (2) "
            + ", ".join(f"[{c}]" for c in selected)
            + " FROM techscope.FactAIRequest "
            + f"ORDER BY [{order_col}] DESC"
        )
        cur.execute(sql)
        rows = cur.fetchall()

        cur.execute(
            "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest"
        )
        current_count = int(cur.fetchone()[0])

        print(f"FACT_AI_REQUEST_CURRENT_ROWS={current_count}", flush=True)
        if baseline is not None:
            print(f"FACT_AI_REQUEST_BASELINE_ROWS={baseline}", flush=True)
            print(
                f"FACT_AI_REQUEST_DELTA_FROM_FINAL_VERIFY="
                f"{current_count - baseline}",
                flush=True,
            )

        print(
            "FACT_AI_REQUEST_SCHEMA_FIELDS="
            + ",".join(fnames),
            flush=True,
        )

        bridge_req_col = pick(
            bnames,
            ["RequestId", "AIRequestId", "request_id"],
        )

        latest = []
        for idx, row in enumerate(rows, start=1):
            obj = {
                selected[i]: row[i]
                for i in range(len(selected))
            }

            bridge_count = None
            if req_col and bridge_req_col and obj.get(req_col) is not None:
                cur.execute(
                    f"""
                    SELECT COUNT_BIG(*)
                    FROM techscope.BridgeAIRequestTechnology
                    WHERE [{bridge_req_col}]=?
                    """,
                    (obj[req_col],),
                )
                bridge_count = int(cur.fetchone()[0])

            latest.append(
                {
                    "row": idx,
                    "values": {
                        k: (
                            str(v)
                            if v is not None
                            else None
                        )
                        for k, v in obj.items()
                    },
                    "bridge_count": bridge_count,
                }
            )

            print(
                f"LATEST_REQUEST_{idx}_GROUNDED="
                f"{obj.get(grounded_col) if grounded_col else 'COLUMN_MISSING'}",
                flush=True,
            )
            print(
                f"LATEST_REQUEST_{idx}_CITATIONS="
                f"{obj.get(citation_col) if citation_col else 'COLUMN_MISSING'}",
                flush=True,
            )
            print(
                f"LATEST_REQUEST_{idx}_BRIDGE_ROWS="
                f"{bridge_count if bridge_count is not None else 'UNAVAILABLE'}",
                flush=True,
            )

        persistence_state = "UNDETERMINED"
        if grounded_col and len(rows) == 2:
            grounds = [obj["values"].get(grounded_col) for obj in latest]
            normalized = [str(x).lower() for x in grounds]
            has_false = any(
                x in {"0", "false", "none"} for x in normalized
            )
            has_true = any(
                x in {"1", "true"} for x in normalized
            )
            if has_false and has_true:
                persistence_state = "PASS_POSITIVE_AND_NEGATIVE"
            elif has_true and not has_false:
                persistence_state = "FAIL_BOTH_LATEST_GROUNDED"
            elif has_false and not has_true:
                persistence_state = "WARN_BOTH_LATEST_UNGROUNDED"

        print(
            f"GROUNDING_SQL_PERSISTENCE_STATE={persistence_state}",
            flush=True,
        )

        return {
            "baseline_count": baseline,
            "current_count": current_count,
            "delta_from_baseline": (
                current_count - baseline
                if baseline is not None
                else None
            ),
            "fact_schema": fschema,
            "bridge_schema": bschema,
            "request_id_column": req_col,
            "grounded_column": grounded_col,
            "citation_column": citation_col,
            "latest": latest,
            "persistence_state": persistence_state,
        }
    finally:
        conn.close()


def route_diagnostic(env):
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))

    from backend.app.main import app
    from backend.app.grounding_guard import (
        assess_grounding,
        _force_ungrounded,
    )
    from fastapi.routing import APIRoute

    ask_route = None
    for route in app.router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == "/ask"
            and "POST" in set(route.methods or set())
        ):
            ask_route = route
            break

    if ask_route is None:
        raise RuntimeError("ASK_ROUTE_NOT_FOUND")

    endpoint_wrapped = bool(
        getattr(
            ask_route.endpoint,
            "_techscope_grounding_guard_wrapped",
            False,
        )
    )

    model = ask_route.response_model
    model_fields = []
    if model is not None:
        fields = getattr(model, "model_fields", None)
        if fields is None:
            fields = getattr(model, "__fields__", None)
        if isinstance(fields, dict):
            model_fields = sorted(str(x) for x in fields.keys())

    guard_field_declared = "grounding_guard" in model_fields

    negative = assess_grounding(
        "포유류의 대표적인 동물은 뭐가있어?"
    )
    positive = assess_grounding(
        "What role does Azure Databricks play in TechScope?"
    )

    synthetic = _force_ungrounded(
        {
            "answer": "synthetic",
            "grounded": True,
            "citations": [{"title": "x"}],
            "grounded_technology_ids": ["T_SYNTHETIC"],
        },
        negative,
    )

    synthetic_ok = (
        synthetic.get("grounded") is False
        and synthetic.get("citations") == []
        and synthetic.get("grounded_technology_ids") == []
        and (
            (synthetic.get("grounding_guard") or {}).get("status")
            == "BLOCKED_OUT_OF_DOMAIN"
        )
    )

    print(
        f"ASK_ROUTE_GUARD_WRAPPED={'PASS' if endpoint_wrapped else 'FAIL'}",
        flush=True,
    )
    print(
        f"ASK_RESPONSE_MODEL={'NONE' if model is None else getattr(model, '__name__', str(model))}",
        flush=True,
    )
    print(
        f"ASK_RESPONSE_MODEL_FIELDS={','.join(model_fields)}",
        flush=True,
    )
    print(
        f"GROUNDING_GUARD_FIELD_DECLARED_IN_RESPONSE_MODEL="
        f"{'YES' if guard_field_declared else 'NO'}",
        flush=True,
    )
    print(
        f"NEGATIVE_DIRECT_CLASSIFICATION="
        f"{'OUT_OF_DOMAIN' if not negative.get('in_domain') else 'IN_DOMAIN'}",
        flush=True,
    )
    print(
        f"POSITIVE_DIRECT_CLASSIFICATION="
        f"{'IN_DOMAIN' if positive.get('in_domain') else 'OUT_OF_DOMAIN'}",
        flush=True,
    )
    print(
        f"SYNTHETIC_GUARD_TRANSFORM={'PASS' if synthetic_ok else 'FAIL'}",
        flush=True,
    )

    response_model_filters_debug = (
        model is not None
        and not guard_field_declared
    )
    print(
        "NEGATIVE_GUARD_STATUS_NONE_CAUSE="
        + (
            "FASTAPI_RESPONSE_MODEL_FILTER"
            if response_model_filters_debug
            else "NOT_PROVEN"
        ),
        flush=True,
    )

    return {
        "endpoint_wrapped": endpoint_wrapped,
        "response_model": (
            None
            if model is None
            else getattr(model, "__name__", str(model))
        ),
        "response_model_fields": model_fields,
        "guard_field_declared": guard_field_declared,
        "response_model_filters_debug": response_model_filters_debug,
        "negative_classification": negative,
        "positive_classification": positive,
        "synthetic_guard_transform_pass": synthetic_ok,
    }


def main():
    print("GROUNDING_PERSISTENCE_DIAGNOSTIC_V3=START", flush=True)
    print("AI_ASK_CALLS=0", flush=True)
    print("AI_REQUEST_INCREMENT_EXPECTED=0", flush=True)
    print("AZURE_RESOURCE_MUTATION=NO", flush=True)

    env, pid, cmd = live_env()
    persistence = persistence_diagnostic()
    route = route_diagnostic(env)

    if not route["endpoint_wrapped"]:
        raise RuntimeError("GROUNDING_GUARD_WRAPPER_NOT_ACTIVE_IN_PATCHED_APP")
    if not route["synthetic_guard_transform_pass"]:
        raise RuntimeError("GROUNDING_GUARD_SYNTHETIC_TRANSFORM_FAIL")
    if route["negative_classification"].get("in_domain"):
        raise RuntimeError("NEGATIVE_DIRECT_CLASSIFICATION_FAIL")
    if not route["positive_classification"].get("in_domain"):
        raise RuntimeError("POSITIVE_DIRECT_CLASSIFICATION_FAIL")

    result = {
        "status": "PASS",
        "ai_ask_calls": 0,
        "ai_request_increment_expected": 0,
        "live_fastapi_pid": pid,
        "live_fastapi_pid_is_1": pid == 1,
        "live_auto_reload": "--reload" in cmd,
        "persistence": persistence,
        "route": route,
        "azure_resource_mutation": False,
        "environment_values_persisted": False,
    }

    GUARD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GUARD_REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("GROUNDING_GUARD_LOGIC=PASS", flush=True)
    print(
        "GROUNDING_GUARD_DEBUG_FIELD_FILTERING="
        + (
            "CONFIRMED"
            if route["response_model_filters_debug"]
            else "NOT_CONFIRMED"
        ),
        flush=True,
    )

    if persistence["persistence_state"] == "FAIL_BOTH_LATEST_GROUNDED":
        print("NEXT_ACTION=PATCH_SQL_GROUNDING_RECONCILIATION", flush=True)
    else:
        print("NEXT_ACTION=ACTIVATE_PATCH_ON_LIVE_8000", flush=True)

    print(
        "REPORT=results/latest/grounding-persistence-diagnostic-v3.json",
        flush=True,
    )
    print("GROUNDING_PERSISTENCE_DIAGNOSTIC_V3=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
