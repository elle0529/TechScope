#!/usr/bin/env python3
"""TechScope Baseline v1.2 Python structural extractor."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "source" / "rawdata.md"
DEFAULT_OUT = ROOT / "extractor" / "output"

SOURCE_ID = "SRC001"
BR_RE = re.compile(r"\s*<br\s*/?>\s*", re.IGNORECASE)
HEADER_MARKUP_RE = re.compile(r"[*_`]+")
ALIGN_CELL_RE = re.compile(r"^:?-+:?$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalize_header(text: str) -> str:
    text = HEADER_MARKUP_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    buf: list[str] = []
    escaped = False

    for ch in stripped:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            buf.append(ch)
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)

    cells.append("".join(buf).strip())
    return cells


def is_alignment_row(cells: list[str]) -> bool:
    return bool(cells) and all(ALIGN_CELL_RE.match(c.replace(" ", "")) for c in cells)


@dataclass(frozen=True)
class ParsedTable:
    header_line: int
    headers: list[str]
    rows: list[tuple[int, list[str], str]]


def find_source_table(text: str) -> ParsedTable:
    lines = text.splitlines()
    required_tokens = ["대분류", "직접 확인되는 기술", "흐름", "간접기술"]

    for i, line in enumerate(lines):
        if "|" not in line:
            continue

        raw_headers = split_markdown_row(line)
        headers = [normalize_header(h) for h in raw_headers]
        joined = " | ".join(headers)

        if not all(token in joined for token in required_tokens):
            continue

        start = i + 1
        if start < len(lines) and "|" in lines[start]:
            next_cells = split_markdown_row(lines[start])
            if is_alignment_row(next_cells):
                start += 1

        rows: list[tuple[int, list[str], str]] = []

        for j in range(start, len(lines)):
            row_line = lines[j]
            if not row_line.strip().startswith("|"):
                if rows:
                    break
                continue

            cells = split_markdown_row(row_line)
            if is_alignment_row(cells):
                continue

            if len(cells) != len(headers):
                if not rows:
                    continue
                raise ValueError(
                    f"Column count mismatch at line {j+1}: expected {len(headers)}, got {len(cells)}"
                )

            if not any(c.strip() for c in cells):
                continue

            rows.append((j + 1, cells, row_line))

        if not rows:
            raise ValueError("Matching TechScope source table has no data rows.")

        return ParsedTable(i + 1, headers, rows)

    raise ValueError(
        "TechScope source table not found. Expected headers containing: "
        + ", ".join(required_tokens)
    )


def choose_column(headers: list[str], token: str) -> int:
    matches = [i for i, h in enumerate(headers) if token in h]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one column containing {token!r}, got {matches}")
    return matches[0]


def structural_items(cell: str) -> list[str]:
    parts = [p.strip() for p in BR_RE.split(cell)]
    return [p for p in parts if p]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    out_dir = Path(args.out).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else out_dir / "manifest.json"

    if not source.exists():
        print(f"EXTRACTOR=FAIL SOURCE_MISSING={source}")
        return 2

    source_before = source.read_bytes()
    source_hash_before = sha256_bytes(source_before)
    text = source_before.decode("utf-8-sig")

    table = find_source_table(text)
    headers = table.headers

    idx_category = choose_column(headers, "대분류")
    idx_direct = choose_column(headers, "직접 확인되는 기술")
    idx_flow = choose_column(headers, "흐름")
    idx_indirect = choose_column(headers, "간접기술")

    category_rows = []
    technology_rows = []
    relation_rows = []
    company_rows = []
    architecture_rows = []

    category_seq = technology_seq = relation_seq = company_seq = architecture_seq = 0

    for logical_row, (line_no, cells, raw_line) in enumerate(table.rows, start=1):
        row_hash = sha256_bytes(raw_line.encode("utf-8"))
        category_raw = cells[idx_category].strip()
        direct_raw = cells[idx_direct].strip()
        flow_raw = cells[idx_flow].strip()
        indirect_raw = cells[idx_indirect].strip()

        category_seq += 1
        category_rows.append({
            "extract_record_id": f"XC{category_seq:05d}",
            "source_id": SOURCE_ID,
            "source_row_number": logical_row,
            "source_line_number": line_no,
            "source_row_sha256": row_hash,
            "category_raw": category_raw,
            "resolution_status": "unresolved",
        })

        for evidence_type, cell_name, cell_value in [
            ("DIRECT", "direct_technology", direct_raw),
            ("INDIRECT", "indirect_technology", indirect_raw),
        ]:
            for item_no, item in enumerate(structural_items(cell_value), start=1):
                technology_seq += 1
                technology_rows.append({
                    "extract_record_id": f"XT{technology_seq:06d}",
                    "source_id": SOURCE_ID,
                    "source_row_number": logical_row,
                    "source_line_number": line_no,
                    "source_row_sha256": row_hash,
                    "source_cell": cell_name,
                    "item_number": item_no,
                    "evidence_type": evidence_type,
                    "category_raw": category_raw,
                    "technology_raw": item,
                    "resolution_status": "unresolved",
                })

        flow_items = structural_items(flow_raw)
        if not flow_items and flow_raw:
            flow_items = [flow_raw]

        for item_no, item in enumerate(flow_items, start=1):
            relation_seq += 1
            relation_rows.append({
                "extract_record_id": f"XR{relation_seq:06d}",
                "source_id": SOURCE_ID,
                "source_row_number": logical_row,
                "source_line_number": line_no,
                "source_row_sha256": row_hash,
                "item_number": item_no,
                "category_raw": category_raw,
                "flow_fragment_raw": item,
                "relation_resolution_status": "unresolved",
                "evidence_type_resolution_status": "unresolved",
            })

        company_seq += 1
        company_rows.append({
            "extract_record_id": f"XU{company_seq:05d}",
            "source_id": SOURCE_ID,
            "source_row_number": logical_row,
            "source_line_number": line_no,
            "source_row_sha256": row_hash,
            "category_raw": category_raw,
            "direct_cell_raw": direct_raw,
            "flow_cell_raw": flow_raw,
            "indirect_cell_raw": indirect_raw,
            "company_resolution_status": "unresolved",
            "usecase_resolution_status": "unresolved",
        })

        architecture_seq += 1
        architecture_rows.append({
            "extract_record_id": f"XA{architecture_seq:05d}",
            "source_id": SOURCE_ID,
            "source_row_number": logical_row,
            "source_line_number": line_no,
            "source_row_sha256": row_hash,
            "category_raw": category_raw,
            "flow_cell_raw": flow_raw,
            "architecture_layer_resolution_status": "unresolved",
        })

    outputs = {
        "technology.csv": (
            ["extract_record_id","source_id","source_row_number","source_line_number",
             "source_row_sha256","source_cell","item_number","evidence_type",
             "category_raw","technology_raw","resolution_status"],
            technology_rows,
        ),
        "category.csv": (
            ["extract_record_id","source_id","source_row_number","source_line_number",
             "source_row_sha256","category_raw","resolution_status"],
            category_rows,
        ),
        "relation.csv": (
            ["extract_record_id","source_id","source_row_number","source_line_number",
             "source_row_sha256","item_number","category_raw","flow_fragment_raw",
             "relation_resolution_status","evidence_type_resolution_status"],
            relation_rows,
        ),
        "company_usecase.csv": (
            ["extract_record_id","source_id","source_row_number","source_line_number",
             "source_row_sha256","category_raw","direct_cell_raw","flow_cell_raw",
             "indirect_cell_raw","company_resolution_status","usecase_resolution_status"],
            company_rows,
        ),
        "architecture_mapping.csv": (
            ["extract_record_id","source_id","source_row_number","source_line_number",
             "source_row_sha256","category_raw","flow_cell_raw",
             "architecture_layer_resolution_status"],
            architecture_rows,
        ),
    }

    counts = {}
    hashes = {}

    for filename, (fields, rows) in outputs.items():
        target = out_dir / filename
        counts[filename] = write_csv(target, fields, rows)
        hashes[filename] = sha256_file(target)

    source_hash_after = sha256_file(source)
    source_unchanged = source_hash_after == source_hash_before

    manifest = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "component": "CMP_PYTHON",
        "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "source_id": SOURCE_ID,
        "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "source_unchanged": source_unchanged,
        "table_header_line": table.header_line,
        "table_headers": headers,
        "source_data_rows": len(table.rows),
        "outputs": {
            name: {
                "path": str((out_dir / name).relative_to(ROOT)) if (out_dir / name).is_relative_to(ROOT) else str(out_dir / name),
                "rows": counts[name],
                "sha256": hashes[name],
            }
            for name in outputs
        },
        "responsibility_boundary": {
            "performed": [
                "Markdown table recognition",
                "row/cell parsing",
                "<br> structural split",
                "minimum field extraction",
                "basic structural validation",
            ],
            "not_performed": [
                "final normalization",
                "Domain ID resolution",
                "complex joins/aggregation",
                "Gold creation",
                "RAG chunk generation",
            ],
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not source_unchanged:
        print("EXTRACTOR=FAIL SOURCE_CHANGED")
        return 3
    if counts["technology.csv"] <= 0 or counts["category.csv"] <= 0:
        print("EXTRACTOR=FAIL EMPTY_REQUIRED_OUTPUT")
        return 4

    print(f"SOURCE_ROWS={len(table.rows)}")
    for name in outputs:
        print(f"OUTPUT={name} ROWS={counts[name]}")
    print("SOURCE_UNCHANGED=PASS")
    print(f"MANIFEST={manifest_path}")
    print("PYTHON_STRUCTURAL_EXTRACTION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
