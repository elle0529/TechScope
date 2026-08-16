from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from pathlib import Path

from mssql_python import connect

REPO = Path("/workspaces/TechScope")
DL = REPO / "generated" / "powerbi_adls_source"
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


def run(cmd: list[str], *, env=None, capture=True) -> str:
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stdout or "").strip() or "Command failed")
    return (p.stdout or "").strip()


def get_storage_key() -> str:
    key = run([
        "az", "storage", "account", "keys", "list",
        "-g", RG,
        "-n", STORAGE,
        "--query", "[0].value",
        "-o", "tsv",
        "--only-show-errors",
    ])
    if not key:
        raise RuntimeError("Could not obtain ephemeral storage key")
    return key


def download(path: str, filename: str, key: str) -> Path:
    DL.mkdir(parents=True, exist_ok=True)
    dest = DL / filename
    if dest.exists():
        dest.unlink()

    env = dict(os.environ)
    env["AZURE_STORAGE_KEY"] = key

    run([
        "az", "storage", "fs", "file", "download",
        "--account-name", STORAGE,
        "--file-system", FS,
        "--path", path,
        "--destination", str(dest),
        "--auth-mode", "key",
        "--only-show-errors",
    ], env=env)

    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"ADLS download failed: {path}")
    print(f"ADLS_DOWNLOAD=PASS PATH={path} BYTES={dest.stat().st_size}")
    return dest


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [
            {
                str(k or "").strip().lower(): str(v or "").strip()
                for k, v in row.items()
            }
            for row in csv.DictReader(f)
        ]
    print(f"CSV_ROWS={path.name}:{len(rows)}")
    print(
        "CSV_HEADERS="
        + path.name
        + ":"
        + ",".join(rows[0].keys() if rows else [])
    )
    return rows


def listify(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, tuple):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_name(s: str) -> str:
    s = s.casefold()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    return " ".join(s.split())


key = get_storage_key()
try:
    relation_path = download(
        "landing/structured/relation.csv",
        "relation.csv",
        key,
    )
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

relation_rows = read_csv(relation_path)
company_rows = read_csv(company_path)
architecture_rows = read_csv(architecture_path)

# Exact source-contract metrics.
direct_claims = sum(
    1 for r in relation_rows
    if (r.get("evidence_type") or "").strip().upper() == "DIRECT"
)
indirect_claims = sum(
    1 for r in relation_rows
    if (r.get("evidence_type") or "").strip().upper() == "INDIRECT"
)

company_values = {
    (r.get("company_name") or "").strip()
    for r in company_rows
    if (r.get("company_name") or "").strip()
}
company_count = len(company_values)

print(f"ADLS_RELATION_ROWS={len(relation_rows)}")
print(f"ADLS_DIRECT_CLAIMS={direct_claims}")
print(f"ADLS_INDIRECT_CLAIMS={indirect_claims}")
print(f"ADLS_COMPANY_USECASE_ROWS={len(company_rows)}")
print(f"ADLS_COMPANY_DISTINCT_VALUES={company_count}")
print(f"ADLS_ARCHITECTURE_MAPPING_ROWS={len(architecture_rows)}")

if len(relation_rows) == 0:
    raise RuntimeError("relation.csv is empty")
if direct_claims + indirect_claims == 0:
    raise RuntimeError("No DIRECT/INDIRECT claims found in relation.csv")
if len(company_rows) == 0 or company_count == 0:
    raise RuntimeError("No company values found in company_usecase.csv")

conn = connect(CS)
try:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT TechnologyKey,TechnologyId,TechnologyName,CategoryName,SourceId
        FROM techscope.DimTechnology
        ORDER BY TechnologyKey
        """
    )
    technology = cur.fetchall()
    if len(technology) != 515:
        raise RuntimeError(f"Expected 515 technologies, got {len(technology)}")

    by_id = {str(r[1]).strip(): r for r in technology}
    by_name = {normalize_name(str(r[2])): r for r in technology if str(r[2]).strip()}

    mappings: dict[tuple[str, str], tuple[int | None, str | None]] = {}

    # Preferred architecture mapping: resolved RAG chunks.
    rag_records = 0
    rag_mapped_pairs = 0
    with rag_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rag_records += 1
            row = json.loads(line)

            ids = []
            for k in ("technology_ids", "technology_id", "technologyIds"):
                ids.extend(listify(row.get(k)))

            names = []
            for k in ("technology", "technology_names", "technologyNames"):
                names.extend(listify(row.get(k)))

            layers = []
            for k in (
                "architecture_layer", "architecture_layers",
                "architectureLayer", "architectureLayers",
            ):
                layers.extend(listify(row.get(k)))

            evidence = row.get("evidence_type") or row.get("evidenceType")
            evidence = str(evidence).strip() if evidence else None

            resolved = [tid for tid in ids if tid in by_id]
            if not resolved:
                for name in names:
                    hit = by_name.get(normalize_name(name))
                    if hit:
                        resolved.append(str(hit[1]).strip())

            for tid in set(resolved):
                for layer in set(layers):
                    if tid and layer.strip():
                        mappings[(tid, layer.strip())] = (None, evidence)
                        rag_mapped_pairs += 1

    print(f"RAG_RECORDS={rag_records}")
    print(f"RAG_ARCHITECTURE_MAPPING_PAIRS={rag_mapped_pairs}")

    # Merge explicit architecture_mapping.csv.
    csv_mapped_pairs = 0
    for row in architecture_rows:
        tech_name = (row.get("technology") or "").strip()
        layer = (row.get("architecture_layer") or "").strip()
        if not tech_name or not layer:
            continue

        hit = by_name.get(normalize_name(tech_name))
        if hit is None:
            # Conservative fallback: normalized source value is contained in exactly
            # one DimTechnology name, or vice versa.
            needle = normalize_name(tech_name)
            candidates = [
                r for n, r in by_name.items()
                if needle and (needle in n or n in needle)
            ]
            if len(candidates) == 1:
                hit = candidates[0]

        if hit is None:
            continue

        tid = str(hit[1]).strip()
        raw_order = (row.get("layer_order") or "").strip()
        try:
            order = int(raw_order) if raw_order else None
        except ValueError:
            order = None
        evidence = (row.get("evidence_type") or "").strip() or None
        mappings[(tid, layer)] = (order, evidence)
        csv_mapped_pairs += 1

    print(f"CSV_ARCHITECTURE_MAPPING_PAIRS={csv_mapped_pairs}")

    if not mappings:
        raise RuntimeError("No architecture mappings could be resolved")

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
    cur.execute(
        """
        ;WITH OneLayer AS(
            SELECT
                TechnologyId,ArchitectureLayer,LayerOrder,EvidenceType,
                ROW_NUMBER() OVER(
                    PARTITION BY TechnologyId
                    ORDER BY
                        CASE WHEN LayerOrder IS NULL THEN 1 ELSE 0 END,
                        LayerOrder,
                        ArchitectureLayer
                ) rn
            FROM techscope.PbiArchitectureMapping
        )
        INSERT INTO techscope.PbiTechnologyExplorer(
            TechnologyKey,TechnologyId,TechnologyName,CategoryName,
            ArchitectureLayer,LayerOrder,EvidenceType,SourceId
        )
        SELECT
            t.TechnologyKey,t.TechnologyId,t.TechnologyName,t.CategoryName,
            COALESCE(m.ArchitectureLayer,N'Unmapped'),
            m.LayerOrder,m.EvidenceType,t.SourceId
        FROM techscope.DimTechnology t
        LEFT JOIN OneLayer m
          ON m.TechnologyId=t.TechnologyId AND m.rn=1
        """
    )
    conn.commit()

    cur.execute(
        """
        SELECT
            COUNT_BIG(*),
            SUM(CASE WHEN ArchitectureLayer<>N'Unmapped' THEN 1 ELSE 0 END),
            COUNT_BIG(DISTINCT CASE
                WHEN ArchitectureLayer<>N'Unmapped' THEN ArchitectureLayer
            END)
        FROM techscope.PbiTechnologyExplorer
        """
    )
    total, mapped, layers = [int(v or 0) for v in cur.fetchone()]

    if total != 515:
        raise RuntimeError(f"Explorer invariant failed: {total}")
    if mapped == 0 or layers == 0:
        raise RuntimeError(
            f"Architecture mapping remained empty: mapped={mapped}, layers={layers}"
        )

    cur.execute("SELECT COUNT_BIG(*) FROM techscope.FactAIRequest")
    ai_requests = int(cur.fetchone()[0])
    cur.execute(
        "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE Status='success'"
    )
    success = int(cur.fetchone()[0])
    cur.execute(
        "SELECT COUNT_BIG(*) FROM techscope.FactAIRequest WHERE CitationFlag=1"
    )
    citation = int(cur.fetchone()[0])
    cur.execute(
        "SELECT AVG(CONVERT(decimal(18,2),LatencyMs)) FROM techscope.FactAIRequest"
    )
    latency = cur.fetchone()[0] or 0

    cur.execute(
        """
        SELECT COUNT_BIG(DISTINCT CategoryName)
        FROM techscope.DimTechnology
        WHERE CategoryName IS NOT NULL
          AND LTRIM(RTRIM(CategoryName))<>''
        """
    )
    categories = int(cur.fetchone()[0])

    cur.execute("DELETE FROM techscope.PbiExecutiveSummary")
    cur.execute(
        """
        INSERT INTO techscope.PbiExecutiveSummary(
            TotalTechnologies,Categories,Companies,DirectClaims,
            IndirectClaims,ArchitectureLayers,AIRequests,
            SuccessfulRequests,CitationRequests,AvgLatencyMs
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            515, categories, company_count, direct_claims,
            indirect_claims, layers, ai_requests,
            success, citation, latency,
        ),
    )
    conn.commit()

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
            FROM techscope.PbiTechnologyExplorer ORDER BY TechnologyKey
        """,
        "AIRequestDetail.csv": """
            SELECT RequestKey,RequestTimestamp,Status,LatencyMs,
                   RetrievedChunkCount,CitationFlag,FeedbackScore,ModelName
            FROM techscope.vwPbiAIRequestDetail ORDER BY RequestKey
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
    print(f"FINAL_CATEGORY_COUNT={categories}")
    print(f"FINAL_COMPANY_COUNT={company_count}")
    print(f"FINAL_DIRECT_CLAIMS={direct_claims}")
    print(f"FINAL_INDIRECT_CLAIMS={indirect_claims}")
    print(f"FINAL_ARCHITECTURE_MAPPED_TECHNOLOGIES={mapped}")
    print(f"FINAL_ARCHITECTURE_LAYER_COUNT={layers}")
    print("POWER_BI_ADLS_FINALIZE=PASS")
    print("FAKE_VALUES_INSERTED=NO")
finally:
    conn.close()
