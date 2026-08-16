from __future__ import annotations

import unittest

from backend.app.core import SearchHit
from backend.app.rag_service import NO_GROUNDING_ANSWER, RagService


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def retrieve(self, question, top_k):
        self.calls.append((question, top_k))
        return list(self.hits)


class FakeGenerator:
    def __init__(self, answer="grounded answer"):
        self.answer = answer
        self.calls = []

    def generate(self, question, hits):
        self.calls.append((question, list(hits)))
        return self.answer


class FakeSink:
    def __init__(self):
        self.events = []

    def record(self, *, question, result, latency_ms):
        self.events.append((question, result, latency_ms))


class RagServiceTests(unittest.TestCase):
    def test_no_hits_returns_non_grounded_without_llm_call(self):
        retriever = FakeRetriever([])
        generator = FakeGenerator()
        sink = FakeSink()
        service = RagService(retriever, generator, sink, top_k=3)

        result = service.ask("unknown topic")

        self.assertFalse(result.grounded)
        self.assertEqual(result.answer, NO_GROUNDING_ANSWER)
        self.assertEqual(generator.calls, [])
        self.assertEqual(len(sink.events), 1)

    def test_hits_return_citations_and_authoritative_technology_ids(self):
        hit = SearchHit(
            chunk_id="CH0001",
            content="Azure Data Factory copies structured data into Bronze.",
            source_id="SRC001",
            technology=("Azure Data Factory",),
            technology_ids=("T0001",),
            category=("Integration",),
            architecture_layer=("Integration",),
            evidence_type="DIRECT",
        )
        retriever = FakeRetriever([hit])
        generator = FakeGenerator("ADF loads the structured layer into Bronze.")
        sink = FakeSink()
        service = RagService(retriever, generator, sink, top_k=5)

        result = service.ask("What loads Bronze?")

        self.assertTrue(result.grounded)
        self.assertEqual(result.retrieved_chunk_ids, ("CH0001",))
        self.assertEqual(result.grounded_technology_ids, ("T0001",))
        self.assertEqual(result.citations[0].source_id, "SRC001")
        self.assertEqual(len(generator.calls), 1)
        self.assertEqual(len(sink.events), 1)

    def test_empty_question_rejected(self):
        service = RagService(FakeRetriever([]), FakeGenerator())
        with self.assertRaises(ValueError):
            service.ask("   ")


if __name__ == "__main__":
    unittest.main()
