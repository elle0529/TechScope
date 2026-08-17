# Implementation Evidence

| Evidence ID | Component ID | Type | Location |
|---|---|---|---|
| EVD-PYTHON-001 | CMP_PYTHON | SOURCE | extractor/extract.py |
| EVD-PYTHON-002 | CMP_PYTHON | EXECUTION | evidence/python/extractor-run.json |
| EVD-ADF-001 | CMP_ADF | SOURCE | adf/PL_Ingest_TechScope.json |
| EVD-DATABRICKS-001 | CMP_DATABRICKS | SOURCE | databricks/src/01_build_techscope.py |
| EVD-AZURE-SQL-001 | CMP_AZURE_SQL | SOURCE | sql/00_schema.sql |
| EVD-POWER-BI-001 | CMP_POWER_BI | SOURCE | powerbi/model/TechScope_Model.tmdl |
| EVD-AI-SEARCH-001 | CMP_AI_SEARCH | SOURCE | rag/search-index.template.json |
| EVD-AZURE-OPENAI-001 | CMP_AZURE_OPENAI | SOURCE | backend/app/azure_openai_adapter.py |
| EVD-FASTAPI-001 | CMP_FASTAPI | SOURCE | backend/app/main.py |
| EVD-ADLS-001 | CMP_ADLS | SOURCE | infra/bicep/p1-data-rg.bicep |
| EVD-ADLS-002 | CMP_ADLS | EXECUTION | evidence/adls/p1d-deployment.json |
| EVD-ADLS-003 | CMP_ADLS | OUTPUT | evidence/adls/p1d-output.json |
| EVD-ADF-002 | CMP_ADF | EXECUTION | evidence/adf/p1d-execution.json |
| EVD-ADF-003 | CMP_ADF | OUTPUT | evidence/adf/p1d-output.json |
| EVD-DATABRICKS-002 | CMP_DATABRICKS | EXECUTION | evidence/databricks/p1d-execution.json |
| EVD-DATABRICKS-003 | CMP_DATABRICKS | OUTPUT | evidence/databricks/p1d-output.json |
| EVD-AZURE-SQL-002 | CMP_AZURE_SQL | EXECUTION | evidence/azure-sql/p1d-execution.json |
| EVD-AZURE-SQL-003 | CMP_AZURE_SQL | OUTPUT | evidence/azure-sql/p1d-output.json |
| EVD-AI-SEARCH-002 | CMP_AI_SEARCH | EXECUTION | evidence/rag/p2b-cloud-e2e.json |
| EVD-AZURE-OPENAI-002 | CMP_AZURE_OPENAI | EXECUTION | evidence/rag/p2b-cloud-e2e.json |
| EVD-FASTAPI-002 | CMP_FASTAPI | EXECUTION | evidence/rag/p2b-cloud-e2e.json |

<!-- TECHSCOPE_MAIN_FINAL_EVIDENCE:START -->
## MAIN Final Verification Evidence

- Final verification report: `results/latest/main-final-verification.json`
- Final status summary: `results/latest/main-final-status-summary.json`
- P1E relation repair report: `results/latest/p1e-relation-repair.json`
- Teams Prototype report: `results/latest/p3-teams-prototype.json`
- Cosmos blocker report: `results/latest/p3-cosmos-blocker.json`

### P1E Technology Relation

- FactTechnologyRelation rows: `43`
- FK validation: `PASS`
- Silver/Gold relation persistence: `PASS`

### Teams

- Status: `Prototype`
- Teams SDK → FastAPI `/ask` adapter smoke: `PASS`
- SOURCE evidence: `PASS`
- EXECUTION evidence: `PASS`
- Live Teams tenant E2E: `NOT COMPLETED`

### Cosmos DB

- Status: `Blocked`
- Reason: `NO_EXISTING_COSMOS_ACCOUNT`
- Azure resource creation performed: `NO`

### Architecture

- Architecture lint: `PASS`
- Architecture lint checks: `25`

> This block records verified evidence only; it does not upgrade blocked/prototype components.
<!-- TECHSCOPE_MAIN_FINAL_EVIDENCE:END -->

<!-- TECHSCOPE_GROUNDING_EVIDENCE:START -->
## AI Grounding Quality Evidence

- Live activation report: `results/latest/grounding-live-activation-v6.json`
- Persistence diagnostic: `results/latest/grounding-persistence-diagnostic-v3.json`
- Grounding guard configuration: `config/grounding-guard.json`
- Grounding guard source: `backend/app/grounding_guard.py`
- Latest verified RequestKey: `20`
- Latest CitationFlag: `False`
- Latest Bridge rows: `0`
- Live `/demo/grounding-runtime`: `version=v6`, `ask_guard_wrapped=true`
- Live unrelated-question regression:
  - Grounded=False
  - Citations=0
  - Technology IDs=0
- Power BI Snapshot: synchronized after live verification.
<!-- TECHSCOPE_GROUNDING_EVIDENCE:END -->
