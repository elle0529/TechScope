from __future__ import annotations

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import OpenAI
from azure.identity import get_bearer_token_provider

from .core import SearchHit


class AzureHybridRetriever:
    """Classic RAG retriever: app-generated embedding + Azure AI Search hybrid query."""

    def __init__(
        self,
        *,
        search_endpoint: str,
        index_name: str,
        azure_openai_endpoint: str,
        embedding_deployment: str,
    ) -> None:
        credential = DefaultAzureCredential()
        self.search = SearchClient(
            endpoint=search_endpoint,
            index_name=index_name,
            credential=credential,
        )
        token_provider = get_bearer_token_provider(
            credential,
            "https://ai.azure.com/.default",
        )
        endpoint = azure_openai_endpoint.rstrip("/") + "/openai/v1/"
        self.openai = OpenAI(
            base_url=endpoint,
            api_key=token_provider,
        )
        self.embedding_deployment = embedding_deployment

    def _embed(self, text: str) -> list[float]:
        response = self.openai.embeddings.create(
            model=self.embedding_deployment,
            input=text,
        )
        return response.data[0].embedding

    def retrieve(self, question: str, top_k: int) -> list[SearchHit]:
        vector = self._embed(question)
        vector_query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )
        results = self.search.search(
            search_text=question,
            vector_queries=[vector_query],
            top=top_k,
            select=[
                "chunk_id",
                "content",
                "source_id",
                "technology",
                "technology_ids",
                "category",
                "architecture_layer",
                "evidence_type",
                "company",
            ],
        )

        hits: list[SearchHit] = []
        for row in results:
            hits.append(
                SearchHit(
                    chunk_id=str(row["chunk_id"]),
                    content=str(row["content"]),
                    score=row.get("@search.score"),
                    source_id=row.get("source_id"),
                    technology=tuple(row.get("technology") or ()),
                    technology_ids=tuple(row.get("technology_ids") or ()),
                    category=tuple(row.get("category") or ()),
                    architecture_layer=tuple(row.get("architecture_layer") or ()),
                    evidence_type=row.get("evidence_type"),
                    company=tuple(row.get("company") or ()),
                )
            )
        return hits
