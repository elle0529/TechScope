#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/workspaces/TechScope")
REL = ROOT / "extractor/output/relation.csv"
SOURCE = ROOT / "source/rawdata.md"
OUT = ROOT / "results/latest/p1e-relation-pattern-diagnostic.json"

SQL_SERVER = "sql-techscope-dev-239bd206.database.windows.net"
SQL_DATABASE = "sqldb-techscope-dev"

ARROW_TOKENS = ["→", "->", "⇒", "➜", "⟶", "=>", "—>"]
SEPARATORS = ["→", "->", "⇒", "➜", "⟶", "=>", "—>", "/", "+", ",", "·", "|", ">"]

def norm(s):
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def load_dim():
    from mssql_python import connect
    cs = (
        f"Server={SQL_SERVER};Database={SQL_DATABASE};"
        "Authentication=ActiveDirectoryDefault;"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    conn = connect(cs)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TechnologyId, TechnologyName "
            "FROM techscope.DimTechnology ORDER BY TechnologyId"
        )
        return [(str(r[0]), str(r[1])) for r in cur.fetchall()]
    finally:
        conn.close()

def load_rel():
    with REL.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_source_lines():
    if not SOURCE.exists():
        return []
    return SOURCE.read_text(encoding="utf-8", errors="ignore").splitlines()

def contains_name(flow, name):
    return name.lower() in flow.lower()

def token_candidates(flow):
    text = flow
    for sep in ARROW_TOKENS:
        text = text.replace(sep, "|")
    for sep in ["/", "+", ",", "·", ">"]:
        text = text.replace(sep, "|")
    return [norm(x) for x in text.split("|") if norm(x)]

def main():
    rows = load_rel()
    dim = load_dim()
    source_lines = load_source_lines()

    names = sorted(dim, key=lambda x: -len(x[1]))
    arrow_counts = Counter()
    sep_counts = Counter()
    exact_match_count = 0
    multi_exact_count = 0
    samples = []
    unmatched_tokens = Counter()
    token_to_examples = defaultdict(list)

    for i, row in enumerate(rows, 1):
        flow = norm(row.get("flow_fragment_raw"))
        arrows = [a for a in ARROW_TOKENS if a in flow]
        for a in arrows:
            arrow_counts[a] += 1
        for s in SEPARATORS:
            if s in flow:
                sep_counts[s] += 1

        matched = []
        occupied = []
        low = flow.lower()

        for tid, name in names:
            nl = name.lower()
            pos = low.find(nl)
            if pos < 0:
                continue
            end = pos + len(nl)
            overlap = any(not (end <= a or pos >= b) for a, b in occupied)
            if not overlap:
                matched.append((tid, name))
                occupied.append((pos, end))

        if matched:
            exact_match_count += 1
        if len(matched) >= 2:
            multi_exact_count += 1

        toks = token_candidates(flow)
        for tok in toks:
            if len(tok) < 2:
                continue
            if not any(tok.lower() == name.lower() for _, name in dim):
                unmatched_tokens[tok] += 1
                if len(token_to_examples[tok]) < 3:
                    token_to_examples[tok].append(flow)

        src_no = row.get("source_line_number")
        src_text = None
        try:
            n = int(src_no)
            if 1 <= n <= len(source_lines):
                src_text = source_lines[n-1].strip()
        except Exception:
            pass

        samples.append({
            "index": i,
            "extract_record_id": row.get("extract_record_id"),
            "source_row_number": row.get("source_row_number"),
            "source_line_number": row.get("source_line_number"),
            "category_raw": row.get("category_raw"),
            "flow_fragment_raw": flow,
            "matched_technologies": [
                {"technology_id": tid, "technology_name": name}
                for tid, name in matched
            ],
            "token_candidates": toks,
            "source_line_text": src_text,
        })

    report = {
        "relation_rows": len(rows),
        "dim_technology_rows": len(dim),
        "rows_with_any_arrow": sum(
            1 for r in rows
            if any(a in norm(r.get("flow_fragment_raw")) for a in ARROW_TOKENS)
        ),
        "arrow_counts": dict(arrow_counts),
        "separator_counts": dict(sep_counts),
        "rows_with_exact_dim_match": exact_match_count,
        "rows_with_2plus_exact_dim_matches": multi_exact_count,
        "top_unmatched_tokens": [
            {
                "token": tok,
                "count": count,
                "examples": token_to_examples[tok],
            }
            for tok, count in unmatched_tokens.most_common(40)
        ],
        "samples": samples,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("P1E_RELATION_PATTERN_DIAGNOSTIC=PASS")
    print(f"RELATION_ROWS={len(rows)}")
    print(f"DIM_TECHNOLOGY_ROWS={len(dim)}")
    print(f"ROWS_WITH_ANY_ARROW={report['rows_with_any_arrow']}")
    print(f"ARROW_COUNTS={json.dumps(report['arrow_counts'], ensure_ascii=False)}")
    print(f"SEPARATOR_COUNTS={json.dumps(report['separator_counts'], ensure_ascii=False)}")
    print(f"ROWS_WITH_EXACT_DIM_MATCH={exact_match_count}")
    print(f"ROWS_WITH_2PLUS_EXACT_DIM_MATCHES={multi_exact_count}")

    print("----- FLOW SAMPLE START -----")
    for s in samples[:25]:
        matched = ", ".join(
            f"{m['technology_id']}:{m['technology_name']}"
            for m in s["matched_technologies"]
        ) or "-"
        print(
            f"[{s['index']:02d}] "
            f"ROW={s['source_row_number']} LINE={s['source_line_number']} "
            f"CATEGORY={s['category_raw']} "
            f"FLOW={s['flow_fragment_raw']}"
        )
        print(f"     MATCH={matched}")
    print("----- FLOW SAMPLE END -----")

    print("----- TOP UNMATCHED TOKENS START -----")
    for item in report["top_unmatched_tokens"][:25]:
        print(f"{item['count']}x | {item['token']}")
    print("----- TOP UNMATCHED TOKENS END -----")

    print("REPORT=results/latest/p1e-relation-pattern-diagnostic.json")
    print("DATA_MUTATION=NO")
    print("NEXT_ACTION=SEND_CONSOLE_OUTPUT")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
