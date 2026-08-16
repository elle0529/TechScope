# TechScope Python Extractor

Implements only Baseline v1.2 structural extraction for `CMP_PYTHON`.

Input: `source/rawdata.md` (`SRC001`)

Outputs:
- `extractor/output/technology.csv`
- `extractor/output/category.csv`
- `extractor/output/relation.csv`
- `extractor/output/company_usecase.csv`
- `extractor/output/architecture_mapping.csv`

No final normalization, Domain ID resolution, Gold, or RAG generation is performed.
Ambiguous semantic values remain `unresolved` for Databricks.
