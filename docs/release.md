# TechScope Portfolio PoC — Final Release v1.0.0

## Release state

- Status: **FROZEN / RELEASE READY**
- Canonical user command: `.\RUN_TECHSCOPE.ps1`
- Canonical internal command: `python tools/techscope.py all --env dev`
- MAIN Full Regression: `PASS`
- Microsoft Teams Live Tenant E2E: `PASS`
- Cosmos Runtime: `PASS`
- Physical Windows Reboot Cold-start: `PASS`
- Canonical startup idempotence: `PASS`
- Normal startup AI request delta: `0`
- Architecture Lint: `PASS`
- Secret-path safety scan: `PASS`

## Runtime flow

`Teams → DevTunnel → Teams SDK → FastAPI → Azure AI Search → Azure OpenAI → Azure SQL / Cosmos → Power BI`

## Release integrity

- Manifest: `release/TechScope_RELEASE_MANIFEST_v1.0.0.json`
- Final Release Evidence: `evidence/release/final-release-freeze.json`
- Final Release Result: `results/latest/final-release-freeze.json`
- Git tag: `techscope-portfolio-v1.0.0`

## Change policy

This release is frozen. Functional or architecture changes after this point require a new release/version rather than mutation of this release record.