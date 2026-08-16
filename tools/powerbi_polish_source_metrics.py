from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from mssql_python import connect

REPO = Path("/workspaces/TechScope")
SNAPSHOT = REPO / "powerbi" / "demo_snapshot" / "data"

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)

EXCLUDE_PARTS = {
    ".venv", "__pycache__", ".pytest_cache", "node_modules",
    "demo_snapshot", "demo", "results",
}


def candidate_files(filename: str) -> list[Path]:
    found = []
    for path in REPO.rglob(filename):
        if any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        if path.is_file():
            found.append(path)

    def score(p: Path) -> tuple[int, str]:
        s = 0
        text = str(p).lower().replace("\\", "/")
        if "extractor/output" in text:
            s += 100
        if "generated" in text:
            s += 80
        if "landing/structured" in text:
            s += 70
        if "source" in text:
            s += 20
        return (-s, text)

    return sorted(found, key=score)


def first_candidate(filename: str) -> Path | None:
    items = candidate_files(filename)
    return items[0] if items else None


def read_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [
            {str(k or "").strip().lower(): str(v or "").strip()
             for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def jsonl_candidates() -> list[Path]:
    names = ["knowledge_chunks.jsonl"]
    results: list[Path] = []
    for name in names:
        for p in REPO.rglob(name):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            if p.is_file():
                results.append(p)

    def score(p: Path) -> tuple[int, str]:
        text = str(p).lower().replace("\\", "/")
        s = 0
        if "/generated/" in text:
            s += 100
        if "/rag/" in text:
            s += 80
        return (-s, text)

    return sorted(results, key=score)


conn = connect(CS)
try:
    cur = conn.cursor()

    cur.execute("""
        SELECT TechnologyKey, TechnologyId, TechnologyName, CategoryName, SourceId
        FROM techscope.DimTechnology
        ORDER BY TechnologyKey
    """)
    tech_rows = cur.fetchall()
    if len(tech_rows) != 515:
        raise RuntimeError(f"Expected 515 DimTechnology rows, got {len(tech_rows)}")

    tech_by_id = {str(r[1]).strip(): r for r in tech_rows}
    tech_by_name = {
        str(r[2]).strip().casefold(): r for r in tech_rows
        if str(r[2]).strip()
    }

    mapping: dict[tuple[str, str], tuple[int | None, str | None, str]] = {}

    # 1) Prefer resolved RAG chunks because they already contain authoritative
    # technology IDs after Databricks normalization.
    rag_source = None
    for path in jsonl_candidates():
        local_count = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                ids = []
                for key in ("technology_ids", "technology_id", "technologyIds"):
                    ids.extend(as_list(row.get(key)))
                names = []
                for key in ("technology", "technology_names", "technologyNames"):
                    names.extend(as_list(row.get(key)))

                layers = []
                for key in (
                    "architecture_layer", "architecture_layers",
                    "architectureLayer", "architectureLayers",
                ):
                    layers.extend(as_list(row.get(key)))

                evidence = (
                    row.get("evidence_type")
                    or row.get("evidenceType")
                    or None
                )
                evidence = str(evidence).strip() if evidence else None

                resolved_ids = [tid for tid in ids if tid in tech_by_id]
                if not resolved_ids:
                    for name in names:
                        hit = tech_by_name.get(name.casefold())
                        if hit:
                            resolved_ids.append(str(hit[1]).strip())

                for tid in sorted(set(resolved_ids)):
                    for layer in sorted(set(layers)):
                        layer = layer.strip()
                        if not layer:
                            continue
                        mapping[(tid, layer)] = (None, evidence, f"rag:{path.name}")
                        local_count += 1

        if local_count:
            rag_source = path
            print(f"ARCHITECTURE_RAG_SOURCE={path}")
            print(f"ARCHITECTURE_RAG_MAPPING_PAIRS={local_count}")
            break

    # 2) Merge explicit extractor architecture mapping.
    arch_path = first_candidate("architecture_mapping.csv")
    arch_rows = read_csv_rows(arch_path)
    csv_pairs = 0
    for row in arch_rows:
        tid = (
            row.get("technology_id")
            or row.get("technologyid")
            or ""
        ).strip()
        tech_name = (
            row.get("technology")
            or row.get("technology_name")
            or row.get("technologyname")
            or ""
        ).strip()
        layer = (
            row.get("architecture_layer")
            or row.get("architecturelayer")
            or row.get("layer")
            or ""
        ).strip()
        if not layer:
            continue

        if tid not in tech_by_id:
            hit = tech_by_name.get(tech_name.casefold()) if tech_name else None
            if hit:
                tid = str(hit[1]).strip()
        if tid not in tech_by_id:
            continue

        raw_order = (
            row.get("layer_order")
            or row.get("layerorder")
            or ""
        ).strip()
        try:
            order = int(raw_order) if raw_order else None
        except ValueError:
            order = None

        evidence = (
            row.get("evidence_type")
            or row.get("evidencetype")
            or None
        )
        evidence = evidence.strip() if isinstance(evidence, str) and evidence.strip() else None

        mapping[(tid, layer)] = (order, evidence, f"csv:{arch_path.name if arch_path else ''}")
        csv_pairs += 1

    print(f"ARCHITECTURE_CSV_SOURCE={arch_path if arch_path else 'NONE'}")
    print(f"ARCHITECTURE_CSV_MAPPING_PAIRS={csv_pairs}")

    # 3) Company KPI from actual company_usecase.csv.
    company_path = first_candidate("company_usecase.csv")
    company_rows = read_csv_rows(company_path)
    companies = {
        (
            r.get("company_name")
            or r.get("companyname")
            or r.get("company")
            or ""
        ).strip()
        for r in company_rows
    }
    companies.discard("")
    print(f"COMPANY_USECASE_SOURCE={company_path if company_path else 'NONE'}")
    print(f"COMPANY_DISTINCT_COUNT={len(companies)}")

    # 4) Relation claims from actual relation.csv only.
    relation_path = first_candidate("relation.csv")
    relation_rows = read_csv_rows(relation_path)
    direct_claims = 0
    indirect_claims = 0
    for r in relation_rows:
        ev = (
            r.get("evidence_type")
            or r.get("evidencetype")
            or ""
        ).strip().upper()
        if ev == "DIRECT":
            direct_claims += 1
        elif ev == "INDIRECT":
            indirect_claims += 1

    print(f"RELATION_SOURCE={relation_path if relation_path else 'NONE'}")
    print(f"DIRECT_CLAIMS={direct_claims}")
    print(f"INDIRECT_CLAIMS={indirect_claims}")

    # Replace Power BI helper mapping only; canonical mart tables are untouched.
    cur.execute("DELETE FROM techscope.PbiArchitectureMapping")
    for (tid, layer), (order, evidence, source) in sorted(mapping.items()):
        cur.execute(
            """
            INSERT INTO techscope.PbiArchitectureMapping(
                TechnologyId, ArchitectureLayer, LayerOrder, EvidenceType
            ) VALUES(?,?,?,?)
            """,
            (tid, layer, order, evidence),
        )
    conn.commit()

    # One deterministic layer per Technology for current demo table.
    cur.execute("DELETE FROM techscope.PbiTechnologyExplorer")
    cur.execute("""
        ;WITH OneLayer AS(
            SELECT
                TechnologyId,
                ArchitectureLayer,
                LayerOrder,
                EvidenceType,
                ROW_NUMBER() OVER(
                    PARTITION BY TechnologyId
                    ORDER BY
                        CASE WHEN LayerOrder IS NULL THEN 1 ELSE 0 END,
                        LayerOrder,
                        ArchitectureLayer
                ) AS rn
            FROM techscope.PbiArchitectureMapping
        )
        INSERT INTO techscope.PbiTechnologyExplorer(
            TechnologyKey, TechnologyId, TechnologyName, CategoryName,
            ArchitectureLayer, LayerOrder, EvidenceType, SourceId
        )
        SELECT
            t.TechnologyKey,
            t.TechnologyId,
            t.TechnologyName,
            t.CategoryName,
            COALESCE(m.ArchitectureLayer, N'Unmapped'),
            m.LayerOrder,
            m.EvidenceType,
            t.SourceId
        FROM techscope.DimTechnology t
        LEFT JOIN OneLayer m
          ON m.TechnologyId=t.TechnologyId AND m.rn=1
    """)
    conn.commit()

    cur.execute("""
        SELECT
            COUNT_BIG(*),
            SUM(CASE WHEN ArchitectureLayer <> N'Unmapped' THEN 1 ELSE 0 END),
            COUNT_BIG(DISTINCT CASE WHEN ArchitectureLayer <> N'Unmapped'
                                    THEN ArchitectureLayer END)
        FROM techscope.PbiTechnologyExplorer
    """)
    total, mapped, layer_count = [int(v or 0) for v in cur.fetchone()]
    if total != 515:
        raise RuntimeError(f"Explorer row count changed: {total}")

    cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
    ai_requests = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE Status='success'")
    successful = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE CitationFlag=1")
    citations = int(cur.fetchone()[0])
    cur.execute("SELECT AVG(CONVERT(decimal(18,2),LatencyMs)) FROM techscope.FactAIRequest")
    avg_latency = cur.fetchone()[0] or 0

    cur.execute("DELETE FROM techscope.PbiExecutiveSummary")
    cur.execute("""
        INSERT INTO techscope.PbiExecutiveSummary(
            TotalTechnologies, Categories, Companies, DirectClaims,
            IndirectClaims, ArchitectureLayers, AIRequests,
            SuccessfulRequests, CitationRequests, AvgLatencyMs
        )
        SELECT
            515,
            COUNT_BIG(DISTINCT NULLIF(LTRIM(RTRIM(CategoryName)),'')),
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        FROM techscope.DimTechnology
    """, (
        len(companies),
        direct_claims,
        indirect_claims,
        layer_count,
        ai_requests,
        successful,
        citations,
        avg_latency,
    ))
    conn.commit()

    # Export refreshed live SQL snapshot.
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    exports = {
        "ExecutiveSummary.csv": """
            SELECT TotalTechnologies,Categories,Companies,DirectClaims,
                   IndirectClaims,ArchitectureLayers,AIRequests,
                   SuccessfulRequests,CitationRequests,AvgLatencyMs
            FROM techscope.PbiExecutiveSummary
        """,
        "TechnologyExplorer.csv": """
            SELECT TechnologyKey,TechnologyId,TechnologyName,CategoryName,
                   ArchitectureLayer,LayerOrder,EvidenceType,SourceId
            FROM techscope.PbiTechnologyExplorer
            ORDER BY TechnologyKey
        """,
        "AIRequestDetail.csv": """
            SELECT RequestKey,RequestTimestamp,Status,LatencyMs,
                   RetrievedChunkCount,CitationFlag,FeedbackScore,ModelName
            FROM techscope.vwPbiAIRequestDetail
            ORDER BY RequestKey
        """,
        "GroundedTechnology.csv": """
            SELECT TechnologyId,TechnologyName,GroundedRequestCount
            FROM techscope.vwPbiGroundedTechnology
            ORDER BY GroundedRequestCount DESC,TechnologyName
        """,
    }

    for filename, sql in exports.items():
        cur.execute(sql)
        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
        with (SNAPSHOT / filename).open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        print(f"SNAPSHOT_REFRESH={filename} ROWS={len(rows)}")

    print(f"TECHNOLOGY_TOTAL={total}")
    print(f"ARCHITECTURE_MAPPED_TECHNOLOGIES={mapped}")
    print(f"ARCHITECTURE_LAYER_COUNT={layer_count}")
    print(f"COMPANY_COUNT_FINAL={len(companies)}")
    print(f"DIRECT_CLAIMS_FINAL={direct_claims}")
    print(f"INDIRECT_CLAIMS_FINAL={indirect_claims}")
    print("POWER_BI_DEMO_POLISH=PASS")
    print("FAKE_METRICS_INSERTED=NO")
finally:
    conn.close()
