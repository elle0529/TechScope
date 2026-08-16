#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print("P2A_ARTIFACT_VALIDATION=FAIL " + message)
    raise SystemExit(1)


def main() -> int:
    required = [
        ROOT / "backend/app/core.py",
        ROOT / "backend/app/rag_service.py",
        ROOT / "backend/app/azure_search_adapter.py",
        ROOT / "backend/app/azure_openai_adapter.py",
        ROOT / "backend/app/main.py",
        ROOT / "backend/requirements-ai.txt",
        ROOT / "rag/search-index.template.json",
        ROOT / "rag/render_search_index.py",
        ROOT / "rag/index_documents.py",
        ROOT / "backend/tests/test_rag_service.py",
    ]
    for path in required:
        if not path.exists():
            fail("missing=" + str(path.relative_to(ROOT)))

    service = (ROOT / "backend/app/rag_service.py").read_text(encoding="utf-8-sig")
    for token in [
        "NO_GROUNDING_ANSWER",
        "retrieved_chunk_ids",
        "grounded_technology_ids",
        "interaction_sink.record",
    ]:
        if token not in service:
            fail("service_token=" + token)

    search = (ROOT / "backend/app/azure_search_adapter.py").read_text(encoding="utf-8-sig")
    for token in [
        "VectorizedQuery",
        "search_text=question",
        "vector_queries=[vector_query]",
        "technology_ids",
        "DefaultAzureCredential",
    ]:
        if token not in search:
            fail("search_token=" + token)

    llm = (ROOT / "backend/app/azure_openai_adapter.py").read_text(encoding="utf-8-sig")
    for token in [
        "/openai/v1/",
        "https://ai.azure.com/.default",
        "responses.create",
        "instructions=SYSTEM_INSTRUCTIONS",
        "response.output_text",
    ]:
        if token not in llm:
            fail("openai_token=" + token)

    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8-sig")
    for token in ['@app.get("/health")', '@app.post("/ask"', "citations", "grounded_technology_ids"]:
        if token not in main:
            fail("fastapi_token=" + token)

    schema_text = (ROOT / "rag/search-index.template.json").read_text(encoding="utf-8-sig")
    schema = json.loads(schema_text)
    names = {x["name"] for x in schema["fields"]}
    expected = {
        "chunk_id","content","source_id","technology","technology_ids",
        "category","architecture_layer","evidence_type","company","content_vector",
    }
    if names != expected:
        fail("search_schema_fields")
    if '"${EMBEDDING_DIMENSIONS}"' not in schema_text:
        fail("search_schema_dimension_parameter")

    # Upstream P1B RAG producer must still exist.
    db = ROOT / "databricks/src/01_build_techscope.py"
    if not db.exists():
        fail("p1b_databricks_missing")
    if "knowledge_chunks.jsonl" not in db.read_text(encoding="utf-8-sig"):
        fail("p1b_rag_contract_missing")

    print("AI_SEARCH_SOURCE_CONTRACT=PASS")
    print("AZURE_OPENAI_SOURCE_CONTRACT=PASS")
    print("FASTAPI_SOURCE_CONTRACT=PASS")
    print("CLASSIC_RAG_GROUNDING_CONTRACT=PASS")
    print("P1B_RAG_UPSTREAM_CONTRACT=PASS")
    print("P2A_ARTIFACT_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
