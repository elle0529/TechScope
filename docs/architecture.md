# TechScope Architecture

## 1. Architecture Principles

This is the live architecture document.

The authoritative frozen architecture contract is:

`docs/baselines/TechScope_Baseline_Architecture_Model_v1.2_FINAL_FROZEN.md`

Frozen Baseline files must not be modified.

## 2. Current MAIN Architecture

```mermaid
flowchart LR
```

## 3. Target MAIN Architecture

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

## 4. Target Key Data Flow

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

## 5. Skill Proof Flow

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

## 6. Component Responsibilities

Component responsibilities follow the Frozen Baseline.

## 7. Significant Decisions

Architecture decisions are stored under:

`docs/decisions/`
