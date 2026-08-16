# TechScope ADF

Canonical pipeline: `PL_Ingest_TechScope`

Purpose:

`/landing/structured` → `/bronze/<entity>/YYYY/MM/DD/<file>.csv`

Pipeline flow:

`Get Metadata → ForEach → Copy Data`

Target files:

- technology.csv
- category.csv
- relation.csv
- company_usecase.csv
- architecture_mapping.csv

`LS_ADLS_TechScope.json` uses the Data Factory system-assigned managed identity
(`authentication: MSI`). `${ADLS_DFS_ENDPOINT}` is rendered by deployment automation.

This directory is Source Artifact only until ADF deployment/run evidence exists.
