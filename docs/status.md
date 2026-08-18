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
| `CMP_COSMOS` | Implemented |
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

<!-- TECHSCOPE_GROUNDING_FIX:START -->
## AI Grounding Quality Fix

- Status: `LIVE VERIFIED`
- Live runtime: `v6`
- False-positive grounding guard: `Implemented`
- Out-of-domain response:
  - Grounded: `False`
  - Citations: `0`
  - Grounded Technology IDs: `0`
- SQL reconciliation:
  - FactAIRequest retained: `YES`
  - CitationFlag: `False`
  - BridgeAIRequestTechnology rows: `0`
- Verified latest RequestKey: `20`
- Current FactAIRequest rows: `20`
- Power BI Snapshot sync: `PASS`

> Out-of-domain requests remain operational requests, but are no longer represented as grounded requests.
<!-- TECHSCOPE_GROUNDING_FIX:END -->


<!-- TECHSCOPE_COSMOS_RUNTIME:START -->
## Cosmos Runtime Persistence

- `CMP_COSMOS = Implemented`
- Authentication: `Microsoft Entra RBAC / DefaultAzureCredential`
- Session persistence: `PASS`
- Conversation persistence: `PASS`
- Feedback persistence: `PASS`
- Account key persisted: `NO`
- Verified session: `ed7ee93c-5f1d-4fe4-9836-8b1eed332d22`
- Verified messages: `2`
- Verified feedback rows: `1`
- AI Requests: `21 -> 22`
<!-- TECHSCOPE_COSMOS_RUNTIME:END -->
