from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    content: str
    score: float | None = None
    source_id: str | None = None
    technology: tuple[str, ...] = ()
    technology_ids: tuple[str, ...] = ()
    category: tuple[str, ...] = ()
    architecture_layer: tuple[str, ...] = ()
    evidence_type: str | None = None
    company: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundingCitation:
    chunk_id: str
    source_id: str | None
    technology: tuple[str, ...]
    technology_ids: tuple[str, ...]
    category: tuple[str, ...]
    architecture_layer: tuple[str, ...]
    evidence_type: str | None
    company: tuple[str, ...]


@dataclass(frozen=True)
class AskResult:
    answer: str
    grounded: bool
    citations: tuple[GroundingCitation, ...] = ()
    retrieved_chunk_ids: tuple[str, ...] = ()
    grounded_technology_ids: tuple[str, ...] = ()


class Retriever(Protocol):
    def retrieve(self, question: str, top_k: int) -> list[SearchHit]:
        ...


class Generator(Protocol):
    def generate(self, question: str, hits: list[SearchHit]) -> str:
        ...


class InteractionSink(Protocol):
    def record(
        self,
        *,
        question: str,
        result: AskResult,
        latency_ms: int,
    ) -> None:
        ...


class NullInteractionSink:
    def record(self, *, question: str, result: AskResult, latency_ms: int) -> None:
        return None
