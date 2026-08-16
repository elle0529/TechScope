from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path

from mssql_python import connect

REPO = Path("/workspaces/TechScope")
DL = REPO / "generated" / "powerbi_adls_source_v6"
SNAPSHOT = REPO / "powerbi" / "demo_snapshot" / "data"

RG = "rg-techscope-dev-239bd206"
STORAGE = "sttechscopedev239bd206"
FS = "techscope"

CS = (
    "Server=sql-techscope-dev-239bd206.database.windows.net;"
    "Database=sqldb-techscope-dev;"
    "Authentication=ActiveDirectoryDefault;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
)


def run(cmd: list[str], *, env=None) -> str:
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stdout or "").strip() or "Command failed")
    return (p.stdout or "").strip()


def storage_key() -> str:
    value = run([
        "az", "storage", "account", "keys", "list",
        "-g", RG, "-n", STORAGE,
        "--query", "[0].value", "-o", "tsv",
        "--only-show-errors",
    ])
    if not value:
        raise RuntimeError("STORAGE_KEY=EMPTY")
    return value


def download(adls_path: str, filename: str, key: str) -> Path:
    DL.mkdir(parents=True, exist_ok=True)
    out = DL / filename
    if out.exists():
        out.unlink()

    env = dict(os.environ)
    env["AZURE_STORAGE_KEY"] = key
    run([
        "az", "storage", "fs", "file", "download",
        "--account-name", STORAGE,
        "--file-system", FS,
        "--path", adls_path,
        "--destination", str(out),
        "--auth-mode", "key",
        "--only-show-errors",
    ], env=env)

    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"DOWNLOAD_EMPTY={adls_path}")
    print(f"ADLS_DOWNLOAD=PASS PATH={adls_path} BYTES={out.stat().st_size}")
    return out


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [str(x or "").strip() for x in (reader.fieldnames or [])]
        print(f"CSV_HEADERS={path.name}:{','.join(headers)}")
        rows = []
        for raw in reader:
            rows.append({
                str(k or "").strip().lower(): str(v or "").strip()
                for k, v in raw.items()
            })
    print(f"CSV_ROWS={path.name}:{len(rows)}")
    return rows


def list_field(row: dict, *keys: str) -> list[str]:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, tuple):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value).strip()
        if text:
            return [text]
    return []


key = storage_key()
try:
    company_path = download(
        "landing/structured/company_usecase.csv",
        "company_usecase.csv",
        key,
    )
    architecture_path = download(
        "landing/structured/architecture_mapping.csv",
        "architecture_mapping.csv",
        key,
    )
    rag_path = download(
        "rag/knowledge_chunks.jsonl",
        "knowledge_chunks.jsonl",
        key,
    )
finally:
    key = None

company_rows = csv_rows(company_path)
architecture_rows = csv_rows(architecture_path)

companies = {
    (row.get("company_name") or row.get("company") or "").strip()
    for row in company_rows
}
companies.discard("")
company_count = len(companies)

if company_count == 0:
    raise RuntimeError("COMPANY_COUNT=0_FROM_ACTUAL_COMPANY_USECASE")

rag_records = []
with rag_path.open("r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            rag_records.append(json.loads(line))

print(f"RAG_RECORDS={len(rag_records)}")
if not rag_records:
    raise RuntimeError("RAG_DATASET=EMPTY")

# Domain Evidence KPI:
# Baseline requires one evidence_type per homogeneous RAG chunk.
direct_evidence = 0
indirect_evidence = 0
rag_companies: set[str] = set()

for row in rag_records:
    ev = str(row.get("evidence_type") or row.get("evidenceType") or "").strip().upper()
    if ev == "DIRECT":
        direct_evidence += 1
    elif ev == "INDIRECT":
        indirect_evidence += 1

    for name in list_field(
        row,
        "company_names",
        "company",
        "companyNames",
    ):
        rag_companies.add(name)

if direct_evidence + indirect_evidence == 0:
    raise RuntimeError("RAG_DOMAIN_EVIDENCE=DIRECT_INDIRECT_NOT_FOUND")

# Company source priority remains company_usecase.csv. RAG company metadata is
# only diagnostic because company_usecase.csv is the designed BI source.
print(f"COMPANY_COUNT_FROM_USECASE={company_count}")
print(f"RAG_DISTINCT_COMPANIES={len(rag_companies)}")
print(f"DIRECT_EVIDENCE_RECORDS={direct_evidence}")
print(f"INDIRECT_EVIDENCE_RECORDS={indirect_evidence}")

conn = connect(CS)
try:
    cur = conn.cursor()

    cur.execute("""
        SELECT TechnologyKey,TechnologyId,TechnologyName,CategoryName,SourceId
        FROM techscope.DimTechnology
        ORDER BY TechnologyKey
    """)
    tech = cur.fetchall()
    if len(tech) != 515:
        raise RuntimeError(f"TECHNOLOGY_INVARIANT={len(tech)}")

    by_id = {str(r[1]).strip(): r for r in tech}
    mappings: dict[tuple[str, str], tuple[int | None, str | None]] = {}

    # Actual extractor schema:
    # technology_id, technology_name, category_id, architecture_layer, source_id
    explicit_count = 0
    for row in architecture_rows:
        tid = (
            row.get("technology_id")
            or row.get("technologyid")
            or ""
        ).strip()
        layer = (
            row.get("architecture_layer")
            or row.get("architecturelayer")
            or ""
        ).strip()

        if tid not in by_id or not layer:
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
            or ""
        ).strip() or None

        mappings[(tid, layer)] = (order, evidence)
        explicit_count += 1

    print(f"EXPLICIT_ARCHITECTURE_MAPPINGS={explicit_count}")

    # Merge resolved RAG architecture metadata for technology IDs not covered above.
    rag_pairs = 0
    for row in rag_records:
        ids = list_field(
            row,
            "technology_ids",
            "technology_id",
            "technologyIds",
        )
        layers = list_field(
            row,
            "architecture_layers",
            "architecture_layer",
            "architectureLayers",
            "architectureLayer",
        )
        evidence = str(
            row.get("evidence_type")
            or row.get("evidenceType")
            or ""
        ).strip() or None

        for tid in ids:
            if tid not in by_id:
                continue
            for layer in layers:
                if not layer:
                    continue
                mappings.setdefault((tid, layer), (None, evidence))
                rag_pairs += 1

    print(f"RAG_ARCHITECTURE_PAIRS_SEEN={rag_pairs}")

    if not mappings:
        raise RuntimeError("ARCHITECTURE_MAPPINGS=0")

    cur.execute("DELETE FROM techscope.PbiArchitectureMapping")
    for (tid, layer), (order, evidence) in sorted(mappings.items()):
        cur.execute(
            """
            INSERT INTO techscope.PbiArchitectureMapping(
                TechnologyId,ArchitectureLayer,LayerOrder,EvidenceType
            ) VALUES(?,?,?,?)
            """,
            (tid, layer, order, evidence),
        )
    conn.commit()

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
            TechnologyKey,TechnologyId,TechnologyName,CategoryName,
            ArchitectureLayer,LayerOrder,EvidenceType,SourceId
        )
        SELECT
            t.TechnologyKey,
            t.TechnologyId,
            t.TechnologyName,
            t.CategoryName,
            COALESCE(m.ArchitectureLayer,N'Unmapped'),
            m.LayerOrder,
            COALESCE(m.EvidenceType,N''),
            t.SourceId
        FROM techscope.DimTechnology t
        LEFT JOIN OneLayer m
          ON m.TechnologyId=t.TechnologyId
         AND m.rn=1
    """)
    conn.commit()

    cur.execute("""
        SELECT
            COUNT_BIG(*),
            SUM(CASE WHEN ArchitectureLayer<>N'Unmapped' THEN 1 ELSE 0 END),
            COUNT_BIG(DISTINCT CASE
                WHEN ArchitectureLayer<>N'Unmapped' THEN ArchitectureLayer
            END)
        FROM techscope.PbiTechnologyExplorer
    """)
    total, mapped, layer_count = [int(v or 0) for v in cur.fetchone()]

    if total != 515:
        raise RuntimeError(f"EXPLORER_ROWS={total}")
    if mapped == 0 or layer_count == 0:
        raise RuntimeError(
            f"ARCHITECTURE_RESULT_EMPTY mapped={mapped} layers={layer_count}"
        )

    cur.execute("""
        SELECT COUNT_BIG(DISTINCT CategoryName)
        FROM techscope.DimTechnology
        WHERE CategoryName IS NOT NULL
          AND LTRIM(RTRIM(CategoryName))<>''
    """)
    category_count = int(cur.fetchone()[0])

    cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
    ai_requests = int(cur.fetchone()[0])

    cur.execute("""
        SELECT COUNT_BIG(*)
        FROM techscope.FactAIRequest
        WHERE Status='success'
    """)
    successful = int(cur.fetchone()[0])

    cur.execute("""
        SELECT COUNT_BIG(*)
        FROM techscope.FactAIRequest
        WHERE CitationFlag=1
    """)
    citation_requests = int(cur.fetchone()[0])

    cur.execute("""
        SELECT AVG(CONVERT(decimal(18,2),LatencyMs))
        FROM techscope.FactAIRequest
    """)
    avg_latency = cur.fetchone()[0] or 0

    cur.execute("DELETE FROM techscope.PbiExecutiveSummary")
    cur.execute("""
        INSERT INTO techscope.PbiExecutiveSummary(
            TotalTechnologies,Categories,Companies,DirectClaims,
            IndirectClaims,ArchitectureLayers,AIRequests,
            SuccessfulRequests,CitationRequests,AvgLatencyMs
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        515,
        category_count,
        company_count,
        direct_evidence,
        indirect_evidence,
        layer_count,
        ai_requests,
        successful,
        citation_requests,
        avg_latency,
    ))
    conn.commit()

    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    exports = {
        "ExecutiveSummary.csv": """
            SELECT
                TotalTechnologies,Categories,Companies,DirectClaims,
                IndirectClaims,ArchitectureLayers,AIRequests,
                SuccessfulRequests,CitationRequests,AvgLatencyMs
            FROM techscope.PbiExecutiveSummary
        """,
        "TechnologyExplorer.csv": """
            SELECT
                TechnologyKey,TechnologyId,TechnologyName,CategoryName,
                ArchitectureLayer,LayerOrder,EvidenceType,SourceId
            FROM techscope.PbiTechnologyExplorer
            ORDER BY TechnologyKey
        """,
        "AIRequestDetail.csv": """
            SELECT
                RequestKey,RequestTimestamp,Status,LatencyMs,
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
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        print(f"SNAPSHOT_REFRESH={filename} ROWS={len(rows)}")

    print(f"FINAL_TECHNOLOGY_COUNT={total}")
    print(f"FINAL_CATEGORY_COUNT={category_count}")
    print(f"FINAL_COMPANY_COUNT={company_count}")
    print(f"FINAL_DIRECT_EVIDENCE={direct_evidence}")
    print(f"FINAL_INDIRECT_EVIDENCE={indirect_evidence}")
    print(f"FINAL_ARCHITECTURE_MAPPED_TECHNOLOGIES={mapped}")
    print(f"FINAL_ARCHITECTURE_LAYER_COUNT={layer_count}")
    print("POWER_BI_ADLS_FINALIZE_V6=PASS")
    print("FAKE_VALUES_INSERTED=NO")
finally:
    conn.close()
