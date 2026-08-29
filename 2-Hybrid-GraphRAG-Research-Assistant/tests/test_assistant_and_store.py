from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from assistant import (  # noqa: E402
    ResearchAssistant,
    build_evidence_graph,
    validate_citations,
)
from config import Neo4jConfig  # noqa: E402
from graph_store import (  # noqa: E402
    SCHEMA_QUERIES,
    UPSERT_CITATIONS_QUERY,
    UPSERT_PAPERS_QUERY,
    ResearchGraphStore,
)
from retrieval import Evidence, RetrievalResult  # noqa: E402
from web import AskRequest  # noqa: E402


def evidence() -> Evidence:
    return Evidence(
        evidence_id="R1",
        chunk_id="rag-2020:s00:p00",
        paper_id="rag-2020",
        title="Retrieval-Augmented Generation",
        year=2020,
        section="Architecture",
        text="RAG combines retrieval with generation.",
        abstract="A retrieval-augmented model.",
        source_url="https://arxiv.org/abs/2005.11401",
        authors=("Patrick Lewis",),
        topics=("Retrieval-Augmented Generation",),
        methods=("Dense retrieval",),
        datasets=("Natural Questions",),
        cited_papers=(
            {"paperId": "dpr-2020", "title": "Dense Passage Retrieval"},
        ),
        cited_by=(),
        hybrid_score=0.91,
        semantic_score=0.82,
    )


class FakeRetriever:
    def __init__(self, items):
        self.items = items
        self.calls: list[tuple] = []

    def search(self, question, *, top_k, filters):
        self.calls.append((question, top_k, filters))
        return RetrievalResult(evidence=self.items, elapsed_ms=12)


class FakeResponses:
    def __init__(self, answer="RAG adds retrieved context [R1]."):
        self.answer = answer
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.answer,
            usage=SimpleNamespace(input_tokens=120, output_tokens=18),
        )


class FakeDriver:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute_query(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if "papersProcessed" in query:
            return ([{"papersProcessed": len(kwargs["papers"])}], None, None)
        return ([], None, None)

    def close(self):
        pass


class AssistantAndStoreTests(unittest.TestCase):
    def test_grounded_answer_uses_responses_api_and_metrics(self):
        item = evidence()
        responses = FakeResponses()
        assistant = ResearchAssistant(
            FakeRetriever((item,)),
            SimpleNamespace(responses=responses),
            "gpt-5.6-luna",
        )

        result = assistant.ask("How does RAG work?")

        self.assertEqual(result.answer, "RAG adds retrieved context [R1].")
        self.assertEqual(result.metrics["evidence_count"], 1)
        self.assertEqual(result.metrics["input_tokens"], 120)
        self.assertEqual(responses.calls[0]["model"], "gpt-5.6-luna")
        self.assertFalse(responses.calls[0]["store"])
        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "low"})

    def test_no_evidence_returns_fallback_without_model_call(self):
        responses = FakeResponses()
        assistant = ResearchAssistant(
            FakeRetriever(()), SimpleNamespace(responses=responses), "model"
        )

        result = assistant.ask("How do I bake sourdough?")

        self.assertIn("does not contain sufficiently relevant evidence", result.answer)
        self.assertEqual(result.evidence, ())
        self.assertEqual(responses.calls, [])

    def test_unknown_or_missing_citations_are_rejected(self):
        item = evidence()
        with self.assertRaisesRegex(RuntimeError, "unknown evidence"):
            validate_citations("Unsupported [R9].", (item,))
        with self.assertRaisesRegex(RuntimeError, "did not cite"):
            validate_citations("No citation here.", (item,))

    def test_evidence_graph_projects_relationship_context(self):
        graph = build_evidence_graph((evidence(),))
        relationships = {edge["relationship"] for edge in graph["edges"]}

        self.assertIn("HAS_CHUNK", relationships)
        self.assertIn("AUTHORED", relationships)
        self.assertIn("ABOUT", relationships)
        self.assertIn("USES_METHOD", relationships)
        self.assertIn("CITES", relationships)

    def test_schema_and_writes_use_cypher_25_and_project_labels(self):
        all_queries = (*SCHEMA_QUERIES, UPSERT_PAPERS_QUERY, UPSERT_CITATIONS_QUERY)
        self.assertTrue(all(query.startswith("CYPHER 25") for query in all_queries))
        self.assertTrue(all("Research" in query for query in all_queries))
        self.assertNotIn(":Movie", "\n".join(all_queries))

    @patch("graph_store.GraphDatabase.driver")
    def test_store_uses_one_driver_database_and_parameterized_rows(self, make_driver):
        driver = FakeDriver()
        make_driver.return_value = driver
        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="secret",
            database="portfolio",
        )
        store = ResearchGraphStore(config)
        row = {"paperId": "p1", "cites": [], "chunks": []}

        self.assertEqual(store.upsert_papers([row], "embedding-model"), 1)
        self.assertEqual(store.upsert_citations([row]), 1)

        self.assertEqual(make_driver.call_count, 1)
        self.assertEqual(driver.calls[0][1]["database_"], "portfolio")
        self.assertEqual(driver.calls[0][1]["papers"], [row])
        self.assertEqual(driver.calls[0][1]["embeddingModel"], "embedding-model")

    def test_api_request_validates_bounds(self):
        request = AskRequest(question="What is GraphRAG?", top_k=8)
        self.assertEqual(request.top_k, 8)
        with self.assertRaises(ValidationError):
            AskRequest(question="no", top_k=9)


if __name__ == "__main__":
    unittest.main()
