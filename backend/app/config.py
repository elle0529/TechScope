from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    search_endpoint: str
    search_index: str
    azure_openai_endpoint: str
    generation_deployment: str
    embedding_deployment: str
    top_k: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        required = {
            "TECHSCOPE_SEARCH_ENDPOINT": os.getenv("TECHSCOPE_SEARCH_ENDPOINT"),
            "TECHSCOPE_SEARCH_INDEX": os.getenv("TECHSCOPE_SEARCH_INDEX"),
            "TECHSCOPE_AZURE_OPENAI_ENDPOINT": os.getenv("TECHSCOPE_AZURE_OPENAI_ENDPOINT"),
            "TECHSCOPE_GENERATION_DEPLOYMENT": os.getenv("TECHSCOPE_GENERATION_DEPLOYMENT"),
            "TECHSCOPE_EMBEDDING_DEPLOYMENT": os.getenv("TECHSCOPE_EMBEDDING_DEPLOYMENT"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        return cls(
            search_endpoint=required["TECHSCOPE_SEARCH_ENDPOINT"],
            search_index=required["TECHSCOPE_SEARCH_INDEX"],
            azure_openai_endpoint=required["TECHSCOPE_AZURE_OPENAI_ENDPOINT"],
            generation_deployment=required["TECHSCOPE_GENERATION_DEPLOYMENT"],
            embedding_deployment=required["TECHSCOPE_EMBEDDING_DEPLOYMENT"],
            top_k=int(os.getenv("TECHSCOPE_RAG_TOP_K", "5")),
        )
