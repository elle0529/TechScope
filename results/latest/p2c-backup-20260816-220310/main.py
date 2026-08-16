from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .azure_openai_adapter import AzureOpenAIResponsesGenerator
from .azure_search_adapter import AzureHybridRetriever
from .azure_sql_interaction_sink import AzureSqlInteractionSink
from .config import Settings
from .rag_service import RagService


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class CitationResponse(BaseModel):
    chunk_id: str
    source_id: str | None
    technology: list[str]
    technology_ids: list[str]
    category: list[str]
    architecture_layer: list[str]
    evidence_type: str | None
    company: list[str]


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[CitationResponse]
    retrieved_chunk_ids: list[str]
    grounded_technology_ids: list[str]


def create_app() -> FastAPI:
    settings = Settings.from_env()
    retriever = AzureHybridRetriever(
        search_endpoint=settings.search_endpoint,
        index_name=settings.search_index,
        azure_openai_endpoint=settings.azure_openai_endpoint,
        embedding_deployment=settings.embedding_deployment,
    )
    generator = AzureOpenAIResponsesGenerator(
        endpoint=settings.azure_openai_endpoint,
        deployment=settings.generation_deployment,
    )
    interaction_sink = AzureSqlInteractionSink.from_env(
        model_name=settings.generation_deployment,
    )
    service = RagService(
        retriever,
        generator,
        interaction_sink=interaction_sink,
        top_k=settings.top_k,
    )

    app = FastAPI(title="TechScope API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest) -> AskResponse:
        try:
            result = service.ask(body.question)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return AskResponse(
            answer=result.answer,
            grounded=result.grounded,
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    source_id=c.source_id,
                    technology=list(c.technology),
                    technology_ids=list(c.technology_ids),
                    category=list(c.category),
                    architecture_layer=list(c.architecture_layer),
                    evidence_type=c.evidence_type,
                    company=list(c.company),
                )
                for c in result.citations
            ],
            retrieved_chunk_ids=list(result.retrieved_chunk_ids),
            grounded_technology_ids=list(result.grounded_technology_ids),
        )

    return app


app = create_app()
