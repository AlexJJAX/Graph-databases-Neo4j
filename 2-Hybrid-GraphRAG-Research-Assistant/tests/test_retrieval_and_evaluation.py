from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from evaluate import score_cases  # noqa: E402
from retrieval import (  # noqa: E402
    ResearchRetriever,
    SearchFilters,
    sanitize_fulltext_query,
)


def metadata(chunk_id: str, paper_id: str, semantic_score: float) -> dict:
    return {
        "chunkId": chunk_id,
        "paperId": paper_id,
        "title": f"Title {paper_id}",
        "year": 2020,
        "section": "Findings",
        "text": "Grounded research evidence.",
        "abstract": "Abstract.",
        "sourceUrl": "https://arxiv.org/abs/1234.5678",
        "authors": ["Researcher"],
        "topics": ["Retrieval-Augmented Generation"],
        "methods": ["Hybrid retrieval"],
        "datasets": [],
        "citedPapers": [],
        "citedBy": [],
        "hybridScore": 0.8,
        "semanticScore": semantic_score,
    }


class FakeBackend:
    def __init__(self, items):
        self.items = items
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(items=self.items)


class FakeEmbedder:
    def __init__(self):
        self.queries: list[str] = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.1, 0.2]


class RetrievalAndEvaluationTests(unittest.TestCase):
    def test_lucene_characters_are_removed_without_losing_words(self):
        self.assertEqual(
            sanitize_fulltext_query('GraphRAG: (vector+graph) "evidence"?'),
            "GraphRAG vector graph evidence",
        )

    def test_filters_validate_year_range_and_trim_topic(self):
        with self.assertRaisesRegex(ValueError, "cannot be later"):
            SearchFilters(year_from=2025, year_to=2020)
        self.assertEqual(
            SearchFilters(topic="  RAG  ", year_from=2019).as_query_params(),
            {"topic": "RAG", "yearFrom": 2019, "yearTo": None},
        )

    def test_hybrid_search_passes_ranker_filters_and_original_query_vector(self):
        backend = FakeBackend(
            [
                SimpleNamespace(metadata=metadata("chunk-1", "paper-1", 0.72)),
                SimpleNamespace(metadata=metadata("chunk-2", "paper-2", 0.19)),
                SimpleNamespace(metadata=metadata("chunk-1", "paper-1", 0.72)),
            ]
        )
        embedder = FakeEmbedder()
        retriever = ResearchRetriever(
            driver=None,
            database="neo4j",
            embedder=embedder,
            minimum_semantic_score=0.25,
            backend=backend,
        )

        result = retriever.search(
            "GraphRAG: what connects vectors?",
            top_k=2,
            filters=SearchFilters(topic="RAG", year_from=2019),
        )

        self.assertEqual([item.evidence_id for item in result.evidence], ["R1"])
        self.assertEqual(embedder.queries, ["GraphRAG: what connects vectors?"])
        call = backend.calls[0]
        self.assertEqual(call["query_text"], "GraphRAG what connects vectors")
        self.assertEqual(call["query_vector"], [0.1, 0.2])
        self.assertEqual(call["top_k"], 6)
        self.assertEqual(call["ranker"], "linear")
        self.assertEqual(call["alpha"], 0.65)
        self.assertEqual(call["query_params"]["yearFrom"], 2019)

    def test_empty_question_is_rejected_before_embedding(self):
        embedder = FakeEmbedder()
        retriever = ResearchRetriever(
            driver=None,
            database="neo4j",
            embedder=embedder,
            backend=FakeBackend([]),
        )
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            retriever.search("   ")
        self.assertEqual(embedder.queries, [])

    def test_evaluation_scores_hits_rank_and_negative_rejection(self):
        cases = [
            {"expectedPaperIds": ["p1"]},
            {"expectedPaperIds": ["p2"]},
            {"expectedPaperIds": []},
        ]
        scores = score_cases(cases, [["p1"], ["other", "p2"], []])

        self.assertEqual(scores["hit_rate_at_k"], 1.0)
        self.assertEqual(scores["mean_reciprocal_rank"], 0.75)
        self.assertEqual(scores["negative_rejection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
