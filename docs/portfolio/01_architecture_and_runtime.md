# Architecture and Runtime Flow

## Data plane

1. Source materials are landed in ADLS.
2. Databricks owns normalization, authoritative technology IDs, deduplication, joins, aggregation, Silver/Gold modeling, and RAG-ready data.
3. Gold data is published to Azure SQL for analytics and operational relations.
4. Azure AI Search indexes grounded knowledge.
5. Azure OpenAI generates answers constrained by retrieved context.
6. FastAPI orchestrates Search, OpenAI, grounding verification, SQL operational logging, and Cosmos interaction persistence.
7. Microsoft Teams is the live user interface through Teams SDK and DevTunnel.
8. Power BI consumes the operational snapshot for demonstration and analytics.

## Grounding contract

A valid grounded answer requires retrieved evidence and preserves authoritative technology identifiers and citations. Out-of-domain requests are prevented from receiving false technology/citation grounding.

## Runtime recovery

`RUN_TECHSCOPE.ps1` recovers:

`Docker Engine → techscope-dev → techscope-runtime-net → FastAPI → SQL access → proxy → DevTunnel → Teams direct-node agent`

The runtime also handles:
- transient Docker Linux Engine readiness races,
- missing main-container recreation,
- current-client SQL firewall repair using the existing exact rule,
- direct Node PID ownership for the Teams agent,
- long inference responses without the former 10-second proxy read timeout.