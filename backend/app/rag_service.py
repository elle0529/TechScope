from __future__ import annotations

import time

from .core import (
    AskResult,
    Generator,
    GroundingCitation,
    InteractionSink,
    NullInteractionSink,
    Retriever,
)


NO_GROUNDING_ANSWER = "근거 자료에서 확인할 수 없습니다."


class RagService:
    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        interaction_sink: InteractionSink | None = None,
        *,
        top_k: int = 5,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.interaction_sink = interaction_sink or NullInteractionSink()
        self.top_k = top_k

    def ask(self, question: str) -> AskResult:
        normalized = question.strip()
        if not normalized:
            raise ValueError("question must not be empty")

        started = time.perf_counter()
        hits = self.retriever.retrieve(normalized, self.top_k)

        if not hits:
            result = AskResult(
                answer=NO_GROUNDING_ANSWER,
                grounded=False,
            )
        else:
            answer = self.generator.generate(normalized, hits).strip()
            if not answer:
                answer = NO_GROUNDING_ANSWER

            citations = tuple(
                GroundingCitation(
                    chunk_id=h.chunk_id,
                    source_id=h.source_id,
                    technology=h.technology,
                    technology_ids=h.technology_ids,
                    category=h.category,
                    architecture_layer=h.architecture_layer,
                    evidence_type=h.evidence_type,
                    company=h.company,
                )
                for h in hits
            )

            technology_ids = tuple(
                sorted(
                    {
                        tid
                        for h in hits
                        for tid in h.technology_ids
                        if tid
                    }
                )
            )

            result = AskResult(
                answer=answer,
                grounded=True,
                citations=citations,
                retrieved_chunk_ids=tuple(h.chunk_id for h in hits),
                grounded_technology_ids=technology_ids,
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        self.interaction_sink.record(
            question=normalized,
            result=result,
            latency_ms=latency_ms,
        )
        return result
