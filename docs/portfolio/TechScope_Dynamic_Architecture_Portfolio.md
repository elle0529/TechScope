# TechScope Dynamic Architecture Portfolio

> Generated automatically from the current TechScope Source of Truth.  
> Generated UTC: `2026-08-19T05:55:41.813242+00:00`

## 1. Purpose

TechScope uses Dynamic Architecture so architecture documentation follows the verified implementation state rather than becoming an isolated static artifact.

## 2. Dynamic Architecture — 3 Layer Model

```mermaid
flowchart BT
    L0["L0 · Actual Implementation<br/>Code · Infra · Data · Runtime"]
    L1["L1 · Current / Target Architecture Model<br/>Current · Target · Track · ADR"]
    L2["L2 · Architecture Validation<br/>Status · Evidence · Lint · Integrity"]
    L0 -->|"Reflect actual state"| L1
    L1 -->|"Validate consistency"| L2
    L2 -->|"PASS / FAIL feedback"| L0
```

## 3. Current As-Built Architecture

```mermaid
flowchart LR
    PY["Python Extractor"]
    ADF["Azure Data Factory"]
    ADLS["ADLS Gen2"]
    DBX["Azure Databricks"]
    SQL["Azure SQL<br/>Serving / Data Mart"]
    PBI["Power BI<br/>Analytics / AI Operations"]
    SEARCH["Azure AI Search"]
    AOAI["Azure OpenAI<br/>RAG / Grounding / Citation"]
    API["FastAPI<br/>/ask"]
    TEAMS["Microsoft Teams"]
    FACT["FactAIRequest<br/>Status · Latency · Citation · Grounding"]
    PY --> ADF
    ADF --> ADLS
    ADLS --> DBX
    DBX --> SQL
    SQL --> PBI
    DBX --> SEARCH
    SEARCH --> AOAI
    AOAI --> API
    TEAMS --> API
    API --> FACT
```

## 4. AI Operations Feedback Loop

```mermaid
flowchart LR
    U["User Question"] --> UI["Web UI / Teams"]
    UI --> API["FastAPI /ask"]
    API --> RAG["Azure AI Search + Azure OpenAI<br/>RAG"]
    RAG --> ANS["Grounded Answer + Citation"]
    API --> FACT["FactAIRequest<br/>Status · Latency · Citation · Grounding"]
    FACT --> SYNC["Runtime Snapshot AutoSync"]
    SYNC --> PBI["Power BI Import<br/>Manual Refresh"]
    PBI --> OPS["AI Operations Analytics"]
```

## 5. Current Architecture — Source of Truth Excerpt

```mermaid
flowchart LR
```

## 6. Target Architecture — Source of Truth Excerpt

```mermaid
flowchart LR

CMP_ADLS["ADLS Gen2"]
CMP_PYTHON["Python Extractor"]
CMP_ADF["Azure Data Factory"]
CMP_DATABRICKS["Azure Databricks"]
CMP_AZURE_SQL["Azure SQL"]
CMP_POWER_BI["Power BI"]
CMP_AI_SEARCH["Azure AI Search"]
CMP_AZURE_OPENAI["Azure OpenAI"]
CMP_FASTAPI["FastAPI"]
CMP_COSMOS["Cosmos DB"]
CMP_TEAMS["Microsoft Teams"]

CMP_ADLS -->|raw read| CMP_PYTHON
CMP_PYTHON -->|structured write| CMP_ADLS

CMP_ADLS -->|structured source| CMP_ADF
CMP_ADF -->|bronze write| CMP_ADLS

CMP_ADLS -->|bronze read| CMP_DATABRICKS
CMP_DATABRICKS -->|silver/gold/rag write| CMP_ADLS

CMP_DATABRICKS -->|curated serving| CMP_AZURE_SQL
CMP_AZURE_SQL -->|BI serving| CMP_POWER_BI

CMP_ADLS -->|rag indexing source| CMP_AI_SEARCH
CMP_AI_SEARCH -->|retrieved context| CMP_AZURE_OPENAI
CMP_AZURE_OPENAI -->|generation| CMP_FASTAPI

CMP_FASTAPI -->|conversation state| CMP_COSMOS
CMP_FASTAPI -->|operations metrics| CMP_AZURE_SQL
CMP_FASTAPI -->|employee interface| CMP_TEAMS
```

## 7. Component Status

| Component | Current Status |
|---|---|
| CMP_ADLS | Prototype |
| CMP_PYTHON | Prototype |
| CMP_ADF | Prototype |
| CMP_DATABRICKS | Prototype |
| CMP_AZURE_SQL | Prototype |
| CMP_POWER_BI | In Progress |
| CMP_AI_SEARCH | Prototype |
| CMP_AZURE_OPENAI | Prototype |
| CMP_FASTAPI | Prototype |
| CMP_COSMOS | Planned |
| CMP_TEAMS | Planned |
| CMP_SSIS | Planned |
| CMP_SYNAPSE | Planned |
| CMP_SSAS | Planned |
| CMP_AAS | Planned |
| CMP_MLFLOW | Planned |
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
| `CMP_TEAMS` | Implemented |
| CMP_ADLS | Implemented |
| CMP_ADF | Implemented |
| CMP_DATABRICKS | Implemented |
| CMP_AZURE_SQL | Implemented |
| CMP_POWER_BI | Implemented |
| CMP_AI_SEARCH | Implemented |
| CMP_AZURE_OPENAI | Implemented |
| CMP_FASTAPI | Implemented |
| CMP_COSMOS | Implemented |
| CMP_TEAMS | Implemented |

## 8. Evidence Model

| Evidence Type | Occurrences |
|---|---:|
| SOURCE | 19 |
| EXECUTION | 18 |
| OUTPUT | 15 |

```text
Actual Implementation
  -> Evidence
  -> Component Status
  -> Current Architecture
  -> Validation / PASS or FAIL
```

## 9. Architecture Diagrams Already Defined in Source of Truth

### Source Diagram 1

```mermaid
flowchart LR
```

### Source Diagram 2

```mermaid
flowchart LR

CMP_ADLS["ADLS Gen2"]
CMP_PYTHON["Python Extractor"]
CMP_ADF["Azure Data Factory"]
CMP_DATABRICKS["Azure Databricks"]
CMP_AZURE_SQL["Azure SQL"]
CMP_POWER_BI["Power BI"]
CMP_AI_SEARCH["Azure AI Search"]
CMP_AZURE_OPENAI["Azure OpenAI"]
CMP_FASTAPI["FastAPI"]
CMP_COSMOS["Cosmos DB"]
CMP_TEAMS["Microsoft Teams"]

CMP_ADLS -->|raw read| CMP_PYTHON
CMP_PYTHON -->|structured write| CMP_ADLS

CMP_ADLS -->|structured source| CMP_ADF
CMP_ADF -->|bronze write| CMP_ADLS

CMP_ADLS -->|bronze read| CMP_DATABRICKS
CMP_DATABRICKS -->|silver/gold/rag write| CMP_ADLS

CMP_DATABRICKS -->|curated serving| CMP_AZURE_SQL
CMP_AZURE_SQL -->|BI serving| CMP_POWER_BI

CMP_ADLS -->|rag indexing source| CMP_AI_SEARCH
CMP_AI_SEARCH -->|retrieved context| CMP_AZURE_OPENAI
CMP_AZURE_OPENAI -->|generation| CMP_FASTAPI

CMP_FASTAPI -->|conversation state| CMP_COSMOS
CMP_FASTAPI -->|operations metrics| CMP_AZURE_SQL
CMP_FASTAPI -->|employee interface| CMP_TEAMS
```

### Source Diagram 3

```mermaid
flowchart LR

SRC001["Raw Technology Markdown"]

ZONE_ADLS_RAW["ADLS /landing/raw"]
CMP_PYTHON["Python Extractor"]
ZONE_ADLS_STRUCTURED["ADLS /landing/structured"]
CMP_ADF["Azure Data Factory"]
ZONE_ADLS_BRONZE["ADLS /bronze"]
CMP_DATABRICKS["Azure Databricks"]

ZONE_ADLS_SILVER["ADLS /silver"]
ZONE_ADLS_GOLD["ADLS /gold"]
ZONE_ADLS_RAG["ADLS /rag"]

CMP_AZURE_SQL["Azure SQL"]
CMP_POWER_BI["Power BI"]

CMP_AI_SEARCH["Azure AI Search"]
CMP_AZURE_OPENAI["Azure OpenAI"]
CMP_FASTAPI["FastAPI"]
CMP_COSMOS["Cosmos DB"]
CMP_TEAMS["Microsoft Teams"]

SRC001 --> ZONE_ADLS_RAW
ZONE_ADLS_RAW --> CMP_PYTHON
CMP_PYTHON --> ZONE_ADLS_STRUCTURED

ZONE_ADLS_STRUCTURED --> CMP_ADF
CMP_ADF --> ZONE_ADLS_BRONZE

ZONE_ADLS_BRONZE --> CMP_DATABRICKS

CMP_DATABRICKS --> ZONE_ADLS_SILVER
CMP_DATABRICKS --> ZONE_ADLS_GOLD
CMP_DATABRICKS --> ZONE_ADLS_RAG

ZONE_ADLS_GOLD --> CMP_AZURE_SQL
CMP_AZURE_SQL --> CMP_POWER_BI

ZONE_ADLS_RAG --> CMP_AI_SEARCH
CMP_AI_SEARCH --> CMP_AZURE_OPENAI
CMP_AZURE_OPENAI --> CMP_FASTAPI

CMP_FASTAPI --> CMP_COSMOS
CMP_FASTAPI --> CMP_AZURE_SQL
CMP_FASTAPI --> CMP_TEAMS
```

### Source Diagram 4

```mermaid
flowchart LR

CMP_SSIS["SSIS — Standalone ETL Skill Proof"]
CMP_SYNAPSE["Synapse"]
CMP_SSAS["SSAS"]
CMP_AAS["Azure Analysis Services"]
CMP_MLFLOW["MLflow"]

CMP_AZURE_SQL["Azure SQL"]
CMP_DATABRICKS["Azure Databricks"]

ZONE_ADLS_GOLD["ADLS /gold"]

ZONE_ADLS_GOLD -->|serverless query source| CMP_SYNAPSE

CMP_AZURE_SQL -->|semantic model source| CMP_SSAS
CMP_SSAS -->|tabular deployment| CMP_AAS

CMP_DATABRICKS -->|experiment environment| CMP_MLFLOW
```

## 10. Generated Diagram Files

- `docs/portfolio/diagrams/01_dynamic_architecture_3layer.mmd`
- `docs/portfolio/diagrams/02_current_as_built_architecture.mmd`
- `docs/portfolio/diagrams/03_ai_operations_feedback_loop.mmd`

## 11. Generated Result

- `results/latest/dynamic-architecture-export.json`

## 12. Source Integrity Manifest

- `docs/status.md` — SHA-256 `91c27732dab40b911dbc636c9aeac8a7d853eb3fc546f9ee210be0ca8ab22e5e` — 5,647 bytes
- `docs/architecture.md` — SHA-256 `69719fe7b9dfee65cc3270f081ee87cd7e86bd900b76c364e56eecba58834881` — 3,155 bytes
- `docs/evidence.md` — SHA-256 `92d23765a492a30842b1db2015fcdd66c88a9995bb241c2136da8e6ff844065d` — 6,206 bytes

Frozen Baseline candidates checked: **1**

## 13. Export Contract

**Authoritative inputs**
- `docs/status.md`
- `docs/architecture.md`
- `docs/evidence.md`

**Safety**
- Frozen Baseline documents are read-only.
- Source of Truth documents are read-only.
- Azure resources are neither created nor deleted.
- Secrets are not persisted.
