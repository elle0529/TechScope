# Implementation Status

| Component ID | Component | Track | Scope | Status |
|---|---|---|---|---|
| CMP_ADLS | ADLS Gen2 | MAIN | REQUIRED | Prototype |
| CMP_PYTHON | Python Extractor | MAIN | REQUIRED | Prototype |
| CMP_ADF | Azure Data Factory | MAIN | REQUIRED | Prototype |
| CMP_DATABRICKS | Azure Databricks | MAIN | REQUIRED | Prototype |
| CMP_AZURE_SQL | Azure SQL | MAIN | REQUIRED | Prototype |
| CMP_POWER_BI | Power BI | MAIN | REQUIRED | In Progress |
| CMP_AI_SEARCH | Azure AI Search | MAIN | REQUIRED | Prototype |
| CMP_AZURE_OPENAI | Azure OpenAI | MAIN | REQUIRED | Prototype |
| CMP_FASTAPI | FastAPI | MAIN | REQUIRED | Prototype |
| CMP_COSMOS | Cosmos DB | MAIN | REQUIRED | Planned |
| CMP_TEAMS | Microsoft Teams | MAIN | REQUIRED | Planned |
| CMP_SSIS | SSIS | SKILL_PROOF | REQUIRED | Planned |
| CMP_SYNAPSE | Synapse | SKILL_PROOF | REQUIRED | Planned |
| CMP_SSAS | SSAS | SKILL_PROOF | REQUIRED | Planned |
| CMP_AAS | Azure Analysis Services | SKILL_PROOF | REQUIRED | Planned |
| CMP_MLFLOW | MLflow | SKILL_PROOF | REQUIRED | Planned |

<!-- TECHSCOPE_MAIN_FINAL_STATUS:START -->
## MAIN Final Verification

- Verification: `PASS`
- Portfolio Core Ready: `YES`
- Release Ready: `NO`

| Component | Status |
|---|---|
| `CMP_ADLS` | Implemented |
| `CMP_PYTHON` | Prototype |
| `CMP_ADF` | Implemented |
| `CMP_DATABRICKS` | Implemented |
| `CMP_AZURE_SQL` | Implemented |
| `CMP_POWER_BI` | Implemented |
| `CMP_AI_SEARCH` | Implemented |
| `CMP_AZURE_OPENAI` | Implemented |
| `CMP_FASTAPI` | Implemented |
| `CMP_COSMOS` | Blocked |
| `CMP_TEAMS` | Prototype |

### Verified runtime counts

- DimTechnology: `515`
- DimCategory: `41`
- FactTechnologyRelation: `43`
- FactAIRequest: `16`
- BridgeAIRequestTechnology: `80`

### Release blockers

- CMP_COSMOS: NO_EXISTING_COSMOS_ACCOUNT
- CMP_TEAMS: Prototype only; live Teams tenant E2E not completed

> This block is generated from `results/latest/main-final-status-summary.json`.
<!-- TECHSCOPE_MAIN_FINAL_STATUS:END -->
