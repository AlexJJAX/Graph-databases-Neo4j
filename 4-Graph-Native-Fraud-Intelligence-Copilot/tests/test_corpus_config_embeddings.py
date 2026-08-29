from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import AppConfig, ConfigurationError  # noqa: E402
from corpus import CorpusError, build_document_rows, load_fraud_network  # noqa: E402
from embeddings import OpenAIEmbedder  # noqa: E402


class FakeEmbedder:
    def __init__(self): self.calls = []
    def embed_documents(self, texts, *, batch_size):
        self.calls.append((list(texts), batch_size))
        return [[float(index), 0.2] for index, _ in enumerate(texts)]


class CorpusConfigEmbeddingTests(unittest.TestCase):
    def test_corpus_is_complete_and_contains_benign_counterexample(self):
        payload = load_fraud_network(PROJECT_DIR / "data" / "fraud_network.json")
        self.assertEqual((len(payload["persons"]), len(payload["accounts"]), len(payload["transactions"])), (10, 10, 13))
        self.assertEqual(len(payload["alerts"]), 4)
        benign = next(item for item in payload["alerts"] if item["alertId"] == "ALRT-1001")
        self.assertEqual(benign["status"], "closed")
        self.assertIn("D-001", next(item for item in payload["persons"] if item["personId"] == "P-001")["deviceIds"])

    def test_unknown_transaction_receiver_is_rejected(self):
        source = json.loads((PROJECT_DIR / "data" / "fraud_network.json").read_text())
        source["transactions"][0]["receiverAccountId"] = "A-MISSING"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"; path.write_text(json.dumps(source))
            with self.assertRaisesRegex(CorpusError, "Unknown receiver"):
                load_fraud_network(path)

    def test_account_requires_exactly_one_controller(self):
        source = json.loads((PROJECT_DIR / "data" / "fraud_network.json").read_text())
        source["persons"][1]["accountIds"].append("A-101")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"; path.write_text(json.dumps(source))
            with self.assertRaisesRegex(CorpusError, "exactly one"):
                load_fraud_network(path)

    def test_document_rows_embed_incrementally(self):
        payload = load_fraud_network(PROJECT_DIR / "data" / "fraud_network.json")
        embedder = FakeEmbedder()
        documents, chunks, total, embedded = build_document_rows(payload, {}, embedder)
        existing = {item["chunkId"]: {"contentHash": item["contentHash"], "hasEmbedding": True} for item in chunks}
        second = FakeEmbedder()
        _, reused, total_again, embedded_again = build_document_rows(payload, existing, second)
        self.assertEqual((len(documents), total, embedded), (6, 15, 15))
        self.assertEqual((total_again, embedded_again), (15, 0))
        self.assertFalse(second.calls)
        self.assertTrue(all(item["embedding"] is None for item in reused))

    def test_configuration_validates_fraud_bounds(self):
        environment = {"NEO4J_URI": "bolt://x", "NEO4J_USERNAME": "neo4j", "NEO4J_PASSWORD": "secret", "OPENAI_API_KEY": "key", "FRAUD_MIN_SEMANTIC_SCORE": ".4", "FRAUD_MAX_AGENT_ROUNDS": "7"}
        with patch.dict(os.environ, environment, clear=True): config = AppConfig.from_env()
        self.assertEqual((config.minimum_semantic_score, config.max_agent_rounds), (.4, 7))
        with patch.dict(os.environ, environment | {"FRAUD_MAX_AGENT_ROUNDS": "2"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "between 3 and 8"): AppConfig.from_env()

    def test_embedding_adapter_orders_and_validates_vectors(self):
        endpoint = SimpleNamespace(create=lambda **_: SimpleNamespace(data=[SimpleNamespace(index=1, embedding=[.3, .4]), SimpleNamespace(index=0, embedding=[.1, .2])]))
        embedder = OpenAIEmbedder(SimpleNamespace(embeddings=endpoint), "model", 2)
        self.assertEqual(embedder.embed_documents(["one", "two"]), [[.1, .2], [.3, .4]])
        bad = OpenAIEmbedder(SimpleNamespace(embeddings=SimpleNamespace(create=lambda **_: SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[.1])]))), "model", 2)
        with self.assertRaisesRegex(ValueError, "dimension mismatch"): bad.embed_query("x")


if __name__ == "__main__": unittest.main()
