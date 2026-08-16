#!/usr/bin/env python3
"""TechScope Baseline v1.2 repository/architecture integrity lint.

Normal mode implements Baseline CHECK 01-25.
Release mode adds RELEASE 01-03.

This lint validates repository/document integrity. It does not independently
authenticate live Azure runtime behavior or Mermaid edge semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

STATUS_PATH = ROOT / "docs" / "status.md"
ARCH_PATH = ROOT / "docs" / "architecture.md"
EVIDENCE_PATH = ROOT / "docs" / "evidence.md"
ADR_DIR = ROOT / "docs" / "decisions"
BASELINE_PATH = (
    ROOT
    / "docs"
    / "baselines"
    / "TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md"
)
BASELINE_LOCK_PATH = ROOT / "config" / "frozen-baseline-hashes.json"

VALID_TRACKS = {"MAIN", "SKILL_PROOF"}
VALID_SCOPES = {"REQUIRED", "OPTIONAL"}
VALID_STATUSES = {"Planned", "In Progress", "Implemented", "Prototype", "Blocked"}
VALID_ADR_STATUSES = {"Proposed", "Accepted", "Rejected", "Superseded"}
VALID_EVIDENCE_TYPES = {"SOURCE", "EXECUTION", "OUTPUT"}

VIEW_HEADINGS = {
    "current": "Current MAIN Architecture",
    "target": "Target MAIN Architecture",
    "flow": "Target Key Data Flow",
    "skill": "Skill Proof Flow",
}

ID_RE = re.compile(r"\b(?:CMP_[A-Z0-9_]+|ZONE_[A-Z0-9_]+|SRC[A-Z0-9_]*)\b")
CMP_RE = re.compile(r"\bCMP_[A-Z0-9_]+\b")
ADR_RE = re.compile(r"\bADR-[A-Z0-9_-]+\b", re.IGNORECASE)
EVD_RE = re.compile(r"^EVD-[A-Z0-9_-]+$", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    check: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"check": self.check, "passed": self.passed, "detail": self.detail}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_markdown_table(text: str, required_columns: list[str]) -> list[dict[str, str]]:
    lines = text.splitlines()

    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue

        headers = [c.strip() for c in line.strip().strip("|").split("|")]

        if not all(col in headers for col in required_columns):
            continue

        if idx + 1 >= len(lines):
            continue

        sep = lines[idx + 1].strip()
        if not sep.startswith("|") or "---" not in sep:
            continue

        rows: list[dict[str, str]] = []
        for row_line in lines[idx + 2 :]:
            stripped = row_line.strip()
            if not stripped.startswith("|"):
                break

            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) != len(headers):
                continue

            row = dict(zip(headers, cells))
            if all(not row.get(col, "") for col in required_columns):
                continue
            rows.append(row)

        return rows

    raise ValueError(f"Markdown table with columns {required_columns!r} not found")


def extract_heading_section(text: str, heading_name: str) -> str:
    lines = text.splitlines()
    heading_index = None
    heading_level = None

    heading_pattern = re.compile(
        r"^(#{1,6})\s+(?:\d+(?:\.\d+)*\.?\s+)?"
        + re.escape(heading_name)
        + r"\s*$",
        re.IGNORECASE,
    )

    for idx, line in enumerate(lines):
        m = heading_pattern.match(line.strip())
        if m:
            heading_index = idx
            heading_level = len(m.group(1))
            break

    if heading_index is None or heading_level is None:
        return ""

    out: list[str] = []
    next_heading_re = re.compile(r"^(#{1,6})\s+")

    for line in lines[heading_index + 1 :]:
        m = next_heading_re.match(line.strip())
        if m and len(m.group(1)) <= heading_level:
            break
        out.append(line)

    return "\n".join(out)


def mermaid_blocks(section: str) -> list[str]:
    return re.findall(r"```mermaid\s*\n(.*?)```", section, flags=re.IGNORECASE | re.DOTALL)


def mermaid_declared_nodes(block: str) -> set[str]:
    nodes: set[str] = set()

    declaration_re = re.compile(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=\[|\(|\{)",
        re.MULTILINE,
    )
    nodes.update(declaration_re.findall(block))

    for line in block.splitlines():
        if any(arrow in line for arrow in ("-->", "---", "-.->", "==>")):
            nodes.update(ID_RE.findall(line))

    return nodes


def parse_adrs() -> list[dict[str, object]]:
    adrs: list[dict[str, object]] = []
    if not ADR_DIR.exists():
        return adrs

    for path in sorted(ADR_DIR.glob("*.md")):
        text = read_text(path)
        ids = ADR_RE.findall(text)

        filename_match = ADR_RE.search(path.stem)
        adr_id = (
            filename_match.group(0).upper()
            if filename_match
            else (ids[0].upper() if ids else "")
        )

        status = ""
        status_patterns = [
            r"(?im)^\s*(?:[-*]\s*)?(?:status|\*\*status\*\*)\s*[:|]\s*"
            r"(Proposed|Accepted|Rejected|Superseded)\b",
            r"(?im)^\|\s*Status\s*\|\s*(Proposed|Accepted|Rejected|Superseded)\s*\|",
        ]
        for pattern in status_patterns:
            m = re.search(pattern, text)
            if m:
                status = m.group(1)
                break

        supersedes: list[str] = []
        for line in text.splitlines():
            if re.search(r"\bsupersedes\b", line, flags=re.IGNORECASE):
                supersedes.extend(x.upper() for x in ADR_RE.findall(line))

        components = sorted(set(CMP_RE.findall(text)))

        adrs.append(
            {
                "path": path,
                "id": adr_id,
                "status": status,
                "supersedes": sorted(set(supersedes)),
                "components": components,
            }
        )

    return adrs


def safe_repo_path(location: str) -> tuple[bool, str]:
    raw = location.strip().strip("`")
    if not raw:
        return False, raw

    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False, raw

    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return False, raw

    return resolved.exists(), raw


def duplicate_values(values: Iterable[str]) -> list[str]:
    counter = Counter(values)
    return sorted(k for k, v in counter.items() if v > 1)


def build_checks(release: bool) -> tuple[list[Check], dict[str, object]]:
    required_files = [STATUS_PATH, ARCH_PATH, EVIDENCE_PATH, BASELINE_PATH]
    missing_required = [str(p.relative_to(ROOT)) for p in required_files if not p.exists()]
    if missing_required:
        checks = [Check("INPUT", False, f"Missing required files: {missing_required}")]
        return checks, {"fatal": missing_required}

    status_rows = parse_markdown_table(
        read_text(STATUS_PATH),
        ["Component ID", "Component", "Track", "Scope", "Status"],
    )
    evidence_rows = parse_markdown_table(
        read_text(EVIDENCE_PATH),
        ["Evidence ID", "Component ID", "Type", "Location"],
    )
    arch_text = read_text(ARCH_PATH)
    adrs = parse_adrs()

    component_ids = [r["Component ID"] for r in status_rows]
    registry = {r["Component ID"]: r for r in status_rows}

    evidence_ids = [r["Evidence ID"] for r in evidence_rows if r["Evidence ID"]]
    adr_ids = [str(a["id"]) for a in adrs if a["id"]]

    checks: list[Check] = []

    dup_components = duplicate_values(component_ids)
    checks.append(Check("CHECK 01", not dup_components, f"Duplicate Component IDs: {dup_components}"))

    invalid_evd_ids = sorted(
        eid for eid in evidence_ids if not EVD_RE.match(eid)
    )
    dup_evidence = duplicate_values(evidence_ids)
    checks.append(
        Check(
            "CHECK 02",
            not dup_evidence and not invalid_evd_ids,
            f"Duplicate Evidence IDs: {dup_evidence}; invalid IDs: {invalid_evd_ids}",
        )
    )

    missing_adr_ids = sorted(str(a["path"].name) for a in adrs if not a["id"])
    dup_adrs = duplicate_values(adr_ids)
    checks.append(
        Check(
            "CHECK 03",
            not missing_adr_ids and not dup_adrs,
            f"Duplicate ADR IDs: {dup_adrs}; missing IDs: {missing_adr_ids}",
        )
    )

    invalid_tracks = sorted(
        {r["Track"] for r in status_rows if r["Track"] not in VALID_TRACKS}
    )
    checks.append(Check("CHECK 04", not invalid_tracks, f"Invalid tracks: {invalid_tracks}"))

    invalid_scopes = sorted(
        {r["Scope"] for r in status_rows if r["Scope"] not in VALID_SCOPES}
    )
    checks.append(Check("CHECK 05", not invalid_scopes, f"Invalid scopes: {invalid_scopes}"))

    invalid_statuses = sorted(
        {r["Status"] for r in status_rows if r["Status"] not in VALID_STATUSES}
    )
    checks.append(Check("CHECK 06", not invalid_statuses, f"Invalid statuses: {invalid_statuses}"))

    invalid_adr_statuses = sorted(
        str(a["path"].name)
        for a in adrs
        if a["status"] not in VALID_ADR_STATUSES
    )
    checks.append(
        Check("CHECK 07", not invalid_adr_statuses, f"Invalid ADR statuses: {invalid_adr_statuses}")
    )

    view_sections = {
        key: extract_heading_section(arch_text, heading)
        for key, heading in VIEW_HEADINGS.items()
    }
    view_blocks = {key: mermaid_blocks(section) for key, section in view_sections.items()}
    cardinality = {key: len(blocks) for key, blocks in view_blocks.items()}
    checks.append(
        Check(
            "CHECK 08",
            all(count == 1 for count in cardinality.values()),
            f"Mermaid block cardinality: {cardinality}",
        )
    )

    view_nodes: dict[str, set[str]] = {}
    invalid_node_types: dict[str, list[str]] = {}

    for key, blocks in view_blocks.items():
        block = blocks[0] if len(blocks) == 1 else ""
        nodes = mermaid_declared_nodes(block)
        view_nodes[key] = nodes

        invalid: list[str] = []
        for node in sorted(nodes):
            if key in {"current", "target"}:
                allowed = node.startswith("CMP_")
            elif key == "flow":
                allowed = (
                    node.startswith("CMP_")
                    or node.startswith("ZONE_")
                    or node.startswith("SRC")
                )
            else:
                allowed = node.startswith("CMP_") or node.startswith("ZONE_")

            if not allowed:
                invalid.append(node)

        if invalid:
            invalid_node_types[key] = invalid

    checks.append(
        Check("CHECK 09", not invalid_node_types, f"Invalid node types: {invalid_node_types}")
    )

    all_view_cmp = sorted(
        set().union(*(set(CMP_RE.findall(blocks[0])) if len(blocks) == 1 else set()
                      for blocks in view_blocks.values()))
    )
    unregistered_arch = sorted(set(all_view_cmp) - set(registry))
    checks.append(
        Check(
            "CHECK 10",
            not unregistered_arch,
            f"Unregistered architecture components: {unregistered_arch}",
        )
    )

    unknown_evidence_components = sorted(
        {
            r["Component ID"]
            for r in evidence_rows
            if r["Component ID"] and r["Component ID"] not in registry
        }
    )
    checks.append(
        Check(
            "CHECK 11",
            not unknown_evidence_components,
            f"Unknown evidence components: {unknown_evidence_components}",
        )
    )

    invalid_evidence_types = sorted(
        {r["Type"] for r in evidence_rows if r["Type"] not in VALID_EVIDENCE_TYPES}
    )
    checks.append(
        Check(
            "CHECK 12",
            not invalid_evidence_types,
            f"Invalid evidence types: {invalid_evidence_types}",
        )
    )

    bad_paths: list[str] = []
    for row in evidence_rows:
        ok, raw = safe_repo_path(row["Location"])
        if not ok:
            bad_paths.append(raw)

    checks.append(
        Check(
            "CHECK 13",
            not bad_paths,
            f"Missing/invalid evidence paths: {sorted(set(bad_paths))}",
        )
    )

    types_by_component: dict[str, set[str]] = defaultdict(set)
    for row in evidence_rows:
        if row["Component ID"] in registry and row["Type"] in VALID_EVIDENCE_TYPES:
            types_by_component[row["Component ID"]].add(row["Type"])

    incomplete_implemented = sorted(
        cid
        for cid, row in registry.items()
        if row["Status"] == "Implemented"
        and not {"SOURCE", "EXECUTION", "OUTPUT"}.issubset(types_by_component[cid])
    )
    checks.append(
        Check(
            "CHECK 14",
            not incomplete_implemented,
            f"Incomplete Implemented: {incomplete_implemented}",
        )
    )

    incomplete_prototype = sorted(
        cid
        for cid, row in registry.items()
        if row["Status"] == "Prototype"
        and not {"SOURCE", "EXECUTION"}.issubset(types_by_component[cid])
    )
    checks.append(
        Check(
            "CHECK 15",
            not incomplete_prototype,
            f"Incomplete Prototype: {incomplete_prototype}",
        )
    )

    current_cmp = set(CMP_RE.findall(view_blocks["current"][0])) if len(view_blocks["current"]) == 1 else set()
    target_cmp = set(CMP_RE.findall(view_blocks["target"][0])) if len(view_blocks["target"]) == 1 else set()
    flow_cmp = set(CMP_RE.findall(view_blocks["flow"][0])) if len(view_blocks["flow"]) == 1 else set()
    skill_cmp = set(CMP_RE.findall(view_blocks["skill"][0])) if len(view_blocks["skill"]) == 1 else set()

    current_non_main = sorted(
        cid for cid in current_cmp if cid in registry and registry[cid]["Track"] != "MAIN"
    )
    checks.append(
        Check("CHECK 16", not current_non_main, f"Non-MAIN in Current MAIN: {current_non_main}")
    )

    invalid_current_status = sorted(
        cid
        for cid in current_cmp
        if cid in registry and registry[cid]["Status"] not in {"Implemented", "Prototype"}
    )
    checks.append(
        Check(
            "CHECK 17",
            not invalid_current_status,
            f"Invalid Current MAIN status: {invalid_current_status}",
        )
    )

    implemented_main = {
        cid
        for cid, row in registry.items()
        if row["Track"] == "MAIN" and row["Status"] == "Implemented"
    }
    implemented_main_missing = sorted(implemented_main - current_cmp)
    checks.append(
        Check(
            "CHECK 18",
            not implemented_main_missing,
            f"Implemented MAIN missing: {implemented_main_missing}",
        )
    )

    target_non_main = sorted(
        cid for cid in target_cmp if cid in registry and registry[cid]["Track"] != "MAIN"
    )
    checks.append(
        Check("CHECK 19", not target_non_main, f"Non-MAIN in Target MAIN: {target_non_main}")
    )

    all_main = {cid for cid, row in registry.items() if row["Track"] == "MAIN"}
    target_missing = sorted(all_main - target_cmp)
    target_extra = sorted(target_cmp - all_main)
    checks.append(
        Check(
            "CHECK 20",
            not target_missing and not target_extra,
            f"Target diff: missing={target_missing}, extra={target_extra}",
        )
    )

    flow_non_main = sorted(
        cid for cid in flow_cmp if cid in registry and registry[cid]["Track"] != "MAIN"
    )
    checks.append(
        Check(
            "CHECK 21",
            not flow_non_main,
            f"Non-MAIN in Target Key Data Flow: {flow_non_main}",
        )
    )

    skill_proof_ids = {
        cid for cid, row in registry.items() if row["Track"] == "SKILL_PROOF"
    }
    leaked_skill = sorted(skill_proof_ids & (target_cmp | flow_cmp))
    checks.append(
        Check(
            "CHECK 22",
            not leaked_skill,
            f"Skill Proof leaked into MAIN views: {leaked_skill}",
        )
    )

    required_skill = {
        cid
        for cid, row in registry.items()
        if row["Track"] == "SKILL_PROOF" and row["Scope"] == "REQUIRED"
    }
    skill_missing = sorted(required_skill - skill_cmp)
    checks.append(
        Check(
            "CHECK 23",
            not skill_missing,
            f"Required Skill Proof missing: {skill_missing}",
        )
    )

    adr_unknown_components = sorted(
        {
            cmp_id
            for adr in adrs
            for cmp_id in adr["components"]
            if cmp_id not in registry
        }
    )
    checks.append(
        Check(
            "CHECK 24",
            not adr_unknown_components,
            f"Unknown ADR components: {adr_unknown_components}",
        )
    )

    adr_id_set = set(adr_ids)
    missing_superseded = sorted(
        {
            ref
            for adr in adrs
            for ref in adr["supersedes"]
            if ref not in adr_id_set
        }
    )
    checks.append(
        Check(
            "CHECK 25",
            not missing_superseded,
            f"Missing superseded ADRs: {missing_superseded}",
        )
    )

    integrity_detail = "Frozen baseline hash lock not configured"
    integrity_passed = True
    if BASELINE_LOCK_PATH.exists():
        try:
            lock = json.loads(read_text(BASELINE_LOCK_PATH))
            expected = lock.get(str(BASELINE_PATH.relative_to(ROOT)))
            actual = sha256(BASELINE_PATH)
            integrity_passed = bool(expected) and expected == actual
            integrity_detail = (
                "Frozen baseline hashes: unchanged"
                if integrity_passed
                else f"Frozen baseline hash mismatch: expected={expected}, actual={actual}"
            )
        except Exception as exc:
            integrity_passed = False
            integrity_detail = f"Frozen baseline hash lock error: {exc}"

    checks.append(Check("INTEGRITY 01", integrity_passed, integrity_detail))

    if release:
        required_main_not_ready = sorted(
            cid
            for cid, row in registry.items()
            if row["Track"] == "MAIN"
            and row["Scope"] == "REQUIRED"
            and row["Status"] != "Implemented"
        )
        checks.append(
            Check(
                "RELEASE 01",
                not required_main_not_ready,
                f"Required MAIN not Implemented: {required_main_not_ready}",
            )
        )

        required_skill_not_ready = sorted(
            cid
            for cid, row in registry.items()
            if row["Track"] == "SKILL_PROOF"
            and row["Scope"] == "REQUIRED"
            and row["Status"] != "Implemented"
        )
        checks.append(
            Check(
                "RELEASE 02",
                not required_skill_not_ready,
                f"Required Skill Proof not Implemented: {required_skill_not_ready}",
            )
        )

        blocked_required = sorted(
            cid
            for cid, row in registry.items()
            if row["Scope"] == "REQUIRED" and row["Status"] == "Blocked"
        )
        checks.append(
            Check(
                "RELEASE 03",
                not blocked_required,
                f"Blocked REQUIRED components: {blocked_required}",
            )
        )

    context = {
        "components": len(status_rows),
        "evidence": len(evidence_rows),
        "adrs": len(adrs),
        "views": {
            key: sorted(set(CMP_RE.findall(blocks[0]))) if len(blocks) == 1 else []
            for key, blocks in view_blocks.items()
        },
    }
    return checks, context


def main() -> int:
    parser = argparse.ArgumentParser(prog="architecture_lint")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        checks, context = build_checks(release=args.release)
    except Exception as exc:
        result = {
            "passed": False,
            "mode": "release" if args.release else "normal",
            "checks": [{"check": "FATAL", "passed": False, "detail": str(exc)}],
            "scope": "local deterministic contract verification; not live Azure verification",
        }
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"ARCHITECTURE_LINT=FAIL")
            print(f"FATAL: {exc}")
        return 1

    passed = all(c.passed for c in checks)
    result = {
        "passed": passed,
        "mode": "release" if args.release else "normal",
        "checks": [c.as_dict() for c in checks],
        "context": context,
        "scope": "local deterministic contract verification; not live Azure verification",
    }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            state = "PASS" if check.passed else "FAIL"
            print(f"{check.check}={state} | {check.detail}")
        print(
            ("RELEASE_LINT" if args.release else "ARCHITECTURE_LINT")
            + ("=PASS" if passed else "=FAIL")
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
