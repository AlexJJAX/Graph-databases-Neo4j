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
    FraudGraphStore, LINK_ALERTS_QUERY, LINK_IDENTITIES_QUERY, LINK_TRANSACTIONS_QUERY,
    SCHEMA_QUERIES, UPSERT_CHUNKS_QUERY, UPSERT_TRANSACTIONS_QUERY,
)
from retrieval import FraudEvidenceRetriever, sanitize_fulltext_query  # noqa: E402


class FakeRecord(dict):
    def data(self): return dict(self)


class FakeDriver:
    def __init__(self): self.calls = []; self.closed = False
    def execute_query(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if "personCount" in query and "chunkCount" in query:
            return ([FakeRecord(personCount=0, accountCount=0, transactionCount=0, alertCount=0, caseCount=0, chunkCount=0)], None, None)
        return ([], None, None)
    def verify_connectivity(self): pass
    def close(self): self.closed = True


class FakeBackend:
    def __init__(self, items): self.items = items; self.calls = []
    def search(self, **kwargs): self.calls.append(kwargs); return SimpleNamespace(items=self.items)


class GraphStoreRetrievalTests(unittest.TestCase):
    def test_schema_is_fraud_isolated_and_cypher_25(self):
        self.assertTrue(all(query.startswith("CYPHER 25") for query in SCHEMA_QUERIES))
        self.assertTrue(all("Fraud" in query or "fraud_" in query for query in SCHEMA_QUERIES))
        self.assertNotIn("OpsChunk", "\n".join(SCHEMA_QUERIES))

    def test_write_queries_are_parameterized_cypher_25(self):
        queries = (LINK_IDENTITIES_QUERY, UPSERT_TRANSACTIONS_QUERY, LINK_TRANSACTIONS_QUERY, LINK_ALERTS_QUERY, UPSERT_CHUNKS_QUERY)
        self.assertTrue(all(query.startswith("CYPHER 25") for query in queries))
        self.assertTrue(all("$rows" in query for query in queries))
        self.assertNotIn("CREATE (", "\n".join(queries))

    @patch("graph_store.GraphDatabase.driver")
    def test_store_creates_one_driver_and_uses_database(self, make_driver):
        driver = FakeDriver(); make_driver.return_value = driver
        store = FraudGraphStore(Neo4jConfig("bolt://x", "u", "p", "portfolio"))
        self.assertEqual(store.existing_chunk_state(), {})
        self.assertEqual(make_driver.call_count, 1)
        self.assertTrue(all(kwargs["database_"] == "portfolio" for _, kwargs in driver.calls))

    @patch("graph_store.GraphDatabase.driver")
    def test_ingest_batches_and_preserves_embedding_model(self, make_driver):
        driver = FakeDriver(); make_driver.return_value = driver
        store = FraudGraphStore(Neo4jConfig("bolt://x", "u", "p"))
        payload = {key: [] for key in ("persons", "accounts", "devices", "addresses", "phones", "merchants", "transactions", "alerts", "cases")}
        store.ingest(payload, [], [{"chunkId": "c1"}], "embed")
        query, kwargs = driver.calls[-1]
        self.assertEqual(query, UPSERT_CHUNKS_QUERY)
        self.assertEqual(kwargs["embeddingModel"], "embed")

    def test_fulltext_sanitization(self):
        self.assertEqual(sanitize_fulltext_query('cycle:("device") +phone'), "cycle device phone")
        self.assertEqual(sanitize_fulltext_query("///"), "fraud investigation transaction network")

    def test_hybrid_retrieval_filters_and_deduplicates(self):
        metadata = {"chunkId": "fraud:TYPO-1:00", "text": "Shared device is a signal.", "section": "Pattern", "title": "Guide", "documentId": "TYPO-1", "sourceType": "typology", "accountIds": [], "deviceIds": [], "merchantIds": [], "hybridScore": .9, "semanticScore": .8}
        item = SimpleNamespace(metadata=metadata)
        backend = FakeBackend([item, item])
        retriever = FraudEvidenceRetriever(driver=None, database="neo4j", embedder=SimpleNamespace(embed_query=lambda _: [.1, .2]), minimum_semantic_score=.5, backend=backend)
        result = retriever.search("shared device", account_ids=["A-1"], source_types=["typology"], top_k=5)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].source_id, "fraud:TYPO-1:00")
        self.assertEqual(backend.calls[0]["query_params"]["accountIds"], ["A-1"])
        self.assertEqual(backend.calls[0]["query_vector"], [.1, .2])

    def test_retrieval_rejects_empty_and_unknown_types(self):
        retriever = FraudEvidenceRetriever(driver=None, database="neo4j", embedder=SimpleNamespace(embed_query=lambda _: [.1]), backend=FakeBackend([]))
        with self.assertRaisesRegex(ValueError, "cannot be empty"): retriever.search(" ")
        with self.assertRaisesRegex(ValueError, "typology"): retriever.search("query", source_types=["runbook"])


if __name__ == "__main__": unittest.main()
