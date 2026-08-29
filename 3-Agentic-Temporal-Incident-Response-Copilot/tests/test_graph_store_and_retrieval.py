from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import Neo4jConfig  # noqa: E402
from graph_store import (  # noqa: E402
    SCHEMA_QUERIES,
    UPSERT_ALERTS_QUERY,
    UPSERT_CHUNKS_QUERY,
    UPSERT_DEPENDENCIES_QUERY,
    UPSERT_DEPLOYMENTS_QUERY,
    UPSERT_INCIDENTS_QUERY,
    OperationsGraphStore,
)
from retrieval import OperationalRetriever, sanitize_fulltext_query  # noqa: E402


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakeDriver:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def execute_query(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if "serviceCount" in query and "chunkCount" in query:
            return ([FakeRecord(serviceCount=0, incidentCount=0, deploymentCount=0, alertCount=0, chunkCount=0)], None, None)
        return ([], None, None)

    def verify_connectivity(self):
        pass

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, items):
        self.items = items
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(items=self.items)


class GraphStoreRetrievalTests(unittest.TestCase):
    def test_schema_is_project_isolated_and_cypher_25(self):
        self.assertTrue(all(query.startswith("CYPHER 25") for query in SCHEMA_QUERIES))
        self.assertTrue(all("Ops" in query for query in SCHEMA_QUERIES))
        self.assertNotIn("ResearchChunk", "\n".join(SCHEMA_QUERIES))

    def test_all_write_queries_are_parameterized_cypher_25(self):
        queries = (
            UPSERT_DEPENDENCIES_QUERY,
            UPSERT_DEPLOYMENTS_QUERY,
            UPSERT_INCIDENTS_QUERY,
            UPSERT_ALERTS_QUERY,
            UPSERT_CHUNKS_QUERY,
        )
        self.assertTrue(all(query.startswith("CYPHER 25") for query in queries))
        self.assertTrue(all("$rows" in query for query in queries))
        self.assertNotIn("CREATE (", "\n".join(queries))

    @patch("graph_store.GraphDatabase.driver")
    def test_store_creates_one_driver_and_skips_unknown_property_probe(self, make_driver):
        driver = FakeDriver()
        make_driver.return_value = driver
        store = OperationsGraphStore(
            Neo4jConfig("bolt://localhost:7687", "neo4j", "secret", "portfolio")
        )
        self.assertEqual(store.existing_chunk_state(), {})
        self.assertEqual(make_driver.call_count, 1)
        self.assertFalse(any("contentHash" in query for query, _ in driver.calls))
        self.assertTrue(all(call[1]["database_"] == "portfolio" for call in driver.calls))

    @patch("graph_store.GraphDatabase.driver")
    def test_ingest_batches_rows_and_embedding_model(self, make_driver):
        driver = FakeDriver()
        make_driver.return_value = driver
        store = OperationsGraphStore(Neo4jConfig("bolt://x", "u", "p"))
        payload = {
            "teams": [], "services": [], "commits": [], "deployments": [],
            "incidents": [], "alerts": [],
        }
        store.ingest(payload, [], [], [{"chunkId": "c1"}], "embed-model")
        last_query, last_kwargs = driver.calls[-1]
        self.assertEqual(last_query, UPSERT_CHUNKS_QUERY)
        self.assertEqual(last_kwargs["rows"], [{"chunkId": "c1"}])
        self.assertEqual(last_kwargs["embeddingModel"], "embed-model")

    def test_fulltext_sanitization_removes_lucene_control_characters(self):
        self.assertEqual(sanitize_fulltext_query('timeout:("payment") +retry'), "timeout payment retry")
        self.assertEqual(sanitize_fulltext_query("///"), "incident response operations")

    def test_hybrid_retrieval_filters_and_deduplicates(self):
        metadata = {
            "chunkId": "runbook:r1:00", "text": "Check timeout.",
            "section": "Safe checks", "title": "Timeout triage",
            "sourceId": "r1", "sourceType": "runbook", "serviceIds": ["checkout-api"],
            "incidentId": None, "hybridScore": 0.9, "semanticScore": 0.8,
        }
        item = SimpleNamespace(metadata=metadata)
        backend = FakeBackend([item, item])
        embedder = SimpleNamespace(embed_query=lambda _: [0.1, 0.2])
        retriever = OperationalRetriever(
            driver=None, database="neo4j", embedder=embedder,
            minimum_semantic_score=0.5, backend=backend,
        )
        result = retriever.search(
            "checkout timeout", service_ids=["checkout-api"],
            source_types=["runbook"], top_k=5,
        )
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].source_id, "runbook:r1:00")
        self.assertEqual(backend.calls[0]["query_params"]["serviceIds"], ["checkout-api"])
        self.assertEqual(backend.calls[0]["query_vector"], [0.1, 0.2])

    def test_retrieval_rejects_unknown_source_type_and_empty_query(self):
        retriever = OperationalRetriever(
            driver=None, database="neo4j",
            embedder=SimpleNamespace(embed_query=lambda _: [0.1]),
            backend=FakeBackend([]),
        )
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            retriever.search(" ")
        with self.assertRaisesRegex(ValueError, "runbook or postmortem"):
            retriever.search("query", source_types=["logs"])


if __name__ == "__main__":
    unittest.main()
