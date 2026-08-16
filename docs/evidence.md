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
