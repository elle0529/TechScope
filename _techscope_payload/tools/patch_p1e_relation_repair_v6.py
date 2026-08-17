from __future__ import annotations

from pathlib import Path

P = Path("/workspaces/TechScope/tools/p1e_relation_repair.py")
text = P.read_text(encoding="utf-8")

start = text.find("def normalize_aliases():")
end = text.find("\ndef relation_row_count():", start)

if start < 0 or end < 0:
    raise SystemExit("NORMALIZE_ALIASES_FUNCTION_NOT_FOUND")

replacement = r'''def _relation_name_norm(value):
    import re
    s = str(value or "").strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _relation_semantic_norm(value):
    stop = {
        "microsoft", "azure",
        "service", "services",
        "database", "analytics",
    }
    tokens = [
        t for t in _relation_name_norm(value).split()
        if t not in stop
    ]
    return " ".join(tokens)


def normalize_aliases():
    import csv
    import re

    with DIM_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        dim_rows = list(csv.DictReader(f))

    canon_names = [
        (r["TechnologyId"], (r["TechnologyName"] or "").strip())
        for r in dim_rows
        if (r.get("TechnologyId") or "").strip()
        and (r.get("TechnologyName") or "").strip()
    ]

    hint_groups = {
        "ADF": ["Azure Data Factory", "ADF"],
        "SSAS": [
            "SQL Server Analysis Services",
            "Microsoft SQL Server Analysis Services",
            "SSAS",
        ],
        "Synapse": [
            "Azure Synapse Analytics",
            "Azure Synapse",
            "Synapse",
        ],
        "Power BI": ["Microsoft Power BI", "Power BI"],
        "Teams": ["Microsoft Teams", "Teams"],
        "Azure SQL": [
            "Azure SQL Database",
            "Microsoft Azure SQL Database",
            "Azure SQL",
        ],
        "Cosmos DB": [
            "Azure Cosmos DB",
            "Microsoft Azure Cosmos DB",
            "Cosmos DB",
        ],
        "Data Lake Gen2": [
            "Azure Data Lake Storage Gen2",
            "ADLS Gen2",
            "Data Lake Gen2",
        ],
        "ADLS Gen2": [
            "Azure Data Lake Storage Gen2",
            "ADLS Gen2",
            "Data Lake Gen2",
        ],
        "Analysis Service": [
            "Azure Analysis Services",
            "Analysis Services",
            "Analysis Service",
        ],
        "Analysis Services": [
            "Azure Analysis Services",
            "Analysis Services",
        ],
        "Azure ML": [
            "Azure Machine Learning",
            "Microsoft Azure Machine Learning",
            "Azure ML",
        ],
        "Azure OpenAI": [
            "Azure OpenAI Service",
            "Microsoft Azure OpenAI",
            "Azure OpenAI",
        ],
        "Power Apps": ["Microsoft Power Apps", "Power Apps"],
        "Power Automate": ["Microsoft Power Automate", "Power Automate"],
        "Power Virtual Agents": [
            "Microsoft Power Virtual Agents",
            "Power Virtual Agents",
            "PVA",
        ],
        "Embedded BI": [
            "Power BI Embedded",
            "Microsoft Power BI Embedded",
            "Embedded BI",
        ],
        "Brain Portal": ["Brain Portal"],
        "Data Mart": ["Data Mart", "Datamart"],
        "Azure AI Search": [
            "Azure AI Search",
            "Azure Cognitive Search",
        ],
        "AI Search": [
            "Azure AI Search",
            "Azure Cognitive Search",
            "AI Search",
        ],
        "Databricks": ["Azure Databricks", "Databricks"],
        "Azure Databricks": ["Azure Databricks", "Databricks"],
        "Azure Functions": ["Azure Functions", "Functions"],
        "Logic Apps": ["Azure Logic Apps", "Logic Apps"],
        "API Management": [
            "Azure API Management",
            "API Management",
            "APIM",
        ],
    }

    def choose_canonical(alias, hints):
        alias_raw = _relation_name_norm(alias)
        alias_sem = _relation_semantic_norm(alias)
        scored = []

        for tid, cname in canon_names:
            c_raw = _relation_name_norm(cname)
            c_sem = _relation_semantic_norm(cname)
            score = 0

            if alias_raw and alias_raw == c_raw:
                score = max(score, 100)
            if alias_sem and alias_sem == c_sem:
                score = max(score, 95)

            for hint in hints:
                h_raw = _relation_name_norm(hint)
                h_sem = _relation_semantic_norm(hint)

                if h_raw and h_raw == c_raw:
                    score = max(score, 100)
                if h_sem and h_sem == c_sem:
                    score = max(score, 95)

                if h_sem and len(h_sem) >= 4:
                    if h_sem in c_sem or c_sem in h_sem:
                        score = max(score, 80)

            if score:
                extra = abs(
                    len(c_sem.split()) -
                    min(
                        [len(_relation_semantic_norm(x).split()) for x in hints if x]
                        or [len(alias_sem.split())]
                    )
                )
                scored.append((score, -extra, -len(cname), tid, cname))

        if not scored:
            return None

        scored.sort(reverse=True)
        best = scored[0]
        tied = [x for x in scored if x[:3] == best[:3]]
        if len({x[4] for x in tied}) > 1:
            return None
        return best[4]

    aliases = set()

    if ALIAS_SRC.exists():
        with ALIAS_SRC.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            lower = {h.lower(): h for h in headers}

            alias_col = None
            canon_col = None

            for candidate in [
                "alias", "technology_alias", "alias_name",
                "source_name", "raw_name",
            ]:
                if candidate in lower:
                    alias_col = lower[candidate]
                    break

            for candidate in [
                "canonical_name", "technology_name",
                "canonical", "target_name",
            ]:
                if candidate in lower:
                    canon_col = lower[candidate]
                    break

            canonical_set = {name for _, name in canon_names}

            if alias_col and canon_col:
                for row in reader:
                    a = (row.get(alias_col) or "").strip()
                    c = (row.get(canon_col) or "").strip()
                    if a and c in canonical_set and a != c:
                        aliases.add((a, c))

    for alias, hints in hint_groups.items():
        canonical = choose_canonical(alias, hints)
        if canonical and alias != canonical:
            aliases.add((alias, canonical))

    with RELATION.open("r", encoding="utf-8-sig", newline="") as f:
        relation_rows = list(csv.DictReader(f))

    source_tokens = set()
    for row in relation_rows:
        flow = (row.get("flow_fragment_raw") or "").strip()
        if not flow:
            continue

        tmp = flow
        for sep in ["→", "->", "⇒", "➜", "⟶", "=>", "—>", "/", "·", "+", ",", "|"]:
            tmp = tmp.replace(sep, "\n")

        for token in tmp.splitlines():
            token = re.sub(r"\s+", " ", token).strip()
            token = re.sub(
                r"(에\s*공급|저장.?통합|분석\s*구조|분석|운영|연동|통합|활용|기반|처리)$",
                "",
                token,
            ).strip()

            if 2 <= len(token) <= 80:
                source_tokens.add(token)

    for token in source_tokens:
        t_sem = _relation_semantic_norm(token)
        if len(t_sem) < 3:
            continue

        matches = []
        for _, cname in canon_names:
            c_sem = _relation_semantic_norm(cname)
            if t_sem == c_sem:
                matches.append(cname)

        if len(set(matches)) == 1 and token != matches[0]:
            aliases.add((token, matches[0]))

    normalized = sorted(
        aliases,
        key=lambda x: (x[1].lower(), x[0].lower()),
    )

    ensure_parent(ALIAS_LOCAL)
    with ALIAS_LOCAL.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alias", "canonical_name"])
        w.writerows(normalized)

    return len(normalized)


def local_relation_preflight():
    import csv
    import re

    with DIM_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        dim_rows = list(csv.DictReader(f))

    name_to_id = {
        (r["TechnologyName"] or "").strip(): (r["TechnologyId"] or "").strip()
        for r in dim_rows
        if (r.get("TechnologyName") or "").strip()
        and (r.get("TechnologyId") or "").strip()
    }

    terms = []
    for name, tid in name_to_id.items():
        if len(name) >= 3:
            terms.append((name.lower(), tid, name))

    with ALIAS_LOCAL.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            alias = (r.get("alias") or "").strip()
            canonical = (r.get("canonical_name") or "").strip()
            tid = name_to_id.get(canonical)

            if alias and tid:
                terms.append((alias.lower(), tid, canonical))

    terms = sorted(
        {(a, tid, c) for a, tid, c in terms},
        key=lambda x: (-len(x[0]), x[0]),
    )

    arrow_re = re.compile(r"\s*(?:→|->|⇒|➜|⟶|=>|—>)\s*")

    def mentions(segment):
        low = segment.lower()
        found = []
        occupied = []

        for term, tid, canonical in terms:
            start = 0
            while True:
                idx = low.find(term, start)
                if idx < 0:
                    break

                end = idx + len(term)
                overlap = any(
                    not (end <= a or idx >= b)
                    for a, b in occupied
                )

                if not overlap:
                    occupied.append((idx, end))
                    found.append((idx, tid, canonical))

                start = idx + max(1, len(term))

        found.sort(key=lambda x: x[0])

        result = []
        seen = set()

        for _, tid, canonical in found:
            if tid not in seen:
                result.append((tid, canonical))
                seen.add(tid)

        return result

    resolved = set()
    resolved_fragments = 0
    unresolved_fragments = 0
    sample = []

    with RELATION.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        flow = (row.get("flow_fragment_raw") or "").strip()
        source_id = (row.get("source_id") or "").strip()

        parts = [p.strip() for p in arrow_re.split(flow) if p.strip()]

        if len(parts) < 2:
            unresolved_fragments += 1
            continue

        part_mentions = [mentions(p) for p in parts]
        local_count = 0

        for i in range(len(parts) - 1):
            left = part_mentions[i]
            right = part_mentions[i + 1]

            if not left or not right:
                continue

            for src_id, src_name in left:
                for dst_id, dst_name in right:
                    if src_id == dst_id:
                        continue

                    key = (
                        src_id,
                        dst_id,
                        "flows_to",
                        "DIRECT",
                        source_id,
                    )
                    resolved.add(key)
                    local_count += 1

                    if len(sample) < 12:
                        sample.append(
                            f"{src_id}:{src_name} -> {dst_id}:{dst_name}"
                        )

        if local_count:
            resolved_fragments += 1
        else:
            unresolved_fragments += 1

    return {
        "rows": len(resolved),
        "resolved_fragments": resolved_fragments,
        "unresolved_fragments": unresolved_fragments,
        "sample": sample,
    }
'''

text = text[:start] + replacement + text[end:]

old_main = '''    alias_count = normalize_aliases()
    print(f"DIM_TECHNOLOGY_ROWS={dim_count}", flush=True)
    print(f"NORMALIZED_ALIAS_ROWS={alias_count}", flush=True)

    # Authentication preflight before any cloud mutation.
'''

new_main = '''    alias_count = normalize_aliases()
    print(f"DIM_TECHNOLOGY_ROWS={dim_count}", flush=True)
    print(f"NORMALIZED_ALIAS_ROWS={alias_count}", flush=True)

    preflight = local_relation_preflight()
    print(
        f"LOCAL_RELATION_PREFLIGHT_ROWS={preflight['rows']}",
        flush=True,
    )
    print(
        f"LOCAL_RESOLVED_FRAGMENTS={preflight['resolved_fragments']}",
        flush=True,
    )
    print(
        f"LOCAL_UNRESOLVED_FRAGMENTS={preflight['unresolved_fragments']}",
        flush=True,
    )

    for item in preflight["sample"][:8]:
        print("LOCAL_RELATION_SAMPLE=" + item, flush=True)

    if preflight["rows"] <= 0:
        raise RuntimeError(
            "LOCAL_RELATION_PREFLIGHT_ZERO: Databricks job not submitted"
        )

    # Authentication preflight before any cloud mutation.
'''

if old_main not in text:
    raise SystemExit("MAIN_ALIAS_BLOCK_NOT_FOUND")

text = text.replace(old_main, new_main, 1)

P.write_text(text, encoding="utf-8")
print("P1E_V6_ALIAS_RESOLUTION_PATCH=PASS")
print("P1E_V6_LOCAL_PREFLIGHT_PATCH=PASS")
