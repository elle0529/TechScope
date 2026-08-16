# TechScope Databricks

Primary MAIN artifact:

- `src/01_build_techscope.py`
- `databricks.yml`
- `resources/techscope_job.yml`

The notebook performs the Baseline Databricks responsibility:

Bronze → normalization → Domain ID resolution → relationship resolution → joins
→ Silver → aggregation/curation → Gold → RAG JSONL.

Ambiguous relation/company material is preserved in unresolved datasets rather
than guessed.

This is Source Artifact only until an actual Databricks workspace bundle
validate/deploy/run produces execution evidence.
