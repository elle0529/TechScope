#!/usr/bin/env python3
from __future__ import annotations

import json
import os

import pymssql


def main() -> int:
    server = os.environ["TECHSCOPE_SQL_SERVER"]
    database = os.environ["TECHSCOPE_SQL_DATABASE"]
    user = os.environ["TECHSCOPE_SQL_USER"]
    password = os.environ["TECHSCOPE_SQL_PASSWORD"]

    conn = pymssql.connect(
        server=server,
        user=user,
        password=password,
        database=database,
        login_timeout=30,
        timeout=60,
    )
    cur = conn.cursor()
    counts = {}
    for key, table in [
        ("technology", "techscope.DimTechnology"),
        ("category", "techscope.DimCategory"),
        ("relation", "techscope.FactTechnologyRelation"),
    ]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[key] = int(cur.fetchone()[0])

    cur.execute(
        "SELECT COUNT(*) FROM sys.views v "
        "JOIN sys.schemas s ON s.schema_id=v.schema_id "
        "WHERE s.name='techscope' AND v.name IN "
        "('vwTechnologyOverview','vwCategorySummary','vwAIInteractionSummary')"
    )
    counts["view_count"] = int(cur.fetchone()[0])
    conn.close()

    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
