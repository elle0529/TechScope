# TechScope Agent Instructions

Authoritative architecture contract:
- docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md
- Never modify or overwrite FROZEN baselines.

Implementation plan:
- IMPLEMENTATION_PLAN.md

Canonical validation/runtime:
- python tools/architecture_lint.py
- python tools/techscope.py all --env dev
- python tools/techscope.py resume --env dev
- python tools/techscope.py release --env dev

Source data:
- source/rawdata.md
- Preserve source/rawdata.md content unchanged.

Ownership:
- tools/, automation/, infra/, generated/, extractor/, adf/, databricks/, sql/, rag/, backend/, powerbi/, teams/, ssis/, synapse/, ssas/, training/
- docs/status.md, docs/architecture.md, docs/evidence.md are live operational artifacts only when implementation/evidence actually changes.

Do not:
- redesign the frozen architecture;
- move Databricks normalization/ID resolution/Gold/RAG work into Python;
- invent custom deployment/RAG/parser frameworks;
- claim cloud readiness without actual capability evidence;
- store secrets/tokens/passwords in repository or results.

Long code:
- deliver as repository files, not chat-pasted blocks.

After each implementation unit:
- run relevant deterministic verification;
- run architecture lint;
- preserve successful units;
- resume from the smallest failed unit.
