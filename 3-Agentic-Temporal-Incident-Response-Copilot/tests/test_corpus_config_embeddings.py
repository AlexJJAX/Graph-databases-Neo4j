from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from config import AppConfig, ConfigurationError  # noqa: E402
from corpus import CorpusError, build_document_rows, load_platform  # noqa: E402
from embeddings import OpenAIEmbedder  # noqa: E402


CORPUS_PATH = PROJECT_DIR / "data" / "platform.json"


class FakeEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def embed_documents(self, texts, *, batch_size):
        self.calls.append(list(texts))
        return [[float(index), 0.5] for index, _ in enumerate(texts)]


class CorpusConfigEmbeddingTests(unittest.TestCase):
    def test_curated_corpus_is_valid_and_cross_referenced(self):
        payload = load_platform(CORPUS_PATH)
        self.assertEqual(len(payload["services"]), 9)
        self.assertEqual(len(payload["incidents"]), 4)
        self.assertEqual(len(payload["alerts"]), 9)

    def test_unknown_service_dependency_is_rejected(self):
        payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        payload["services"][0]["dependsOn"][0]["serviceId"] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(CorpusError, "Unknown service dependency"):
                load_platform(path)

    def test_document_rows_embed_only_new_or_changed_chunks(self):
        payload = load_platform(CORPUS_PATH)
        embedder = FakeEmbedder()
        runbooks, postmortems, chunks, total, embedded = build_document_rows(
            payload, {}, embedder, batch_size=7
        )
        existing = {
            chunk["chunkId"]: {
                "contentHash": chunk["contentHash"],
                "hasEmbedding": True,
            }
            for chunk in chunks
        }
        second_embedder = FakeEmbedder()
        _, _, reused_chunks, total_again, embedded_again = build_document_rows(
            payload, existing, second_embedder
        )

        self.assertEqual((len(runbooks), len(postmortems)), (4, 3))
        self.assertEqual(total, 18)
        self.assertEqual(embedded, 18)
        self.assertEqual(total_again, 18)
        self.assertEqual(embedded_again, 0)
        self.assertEqual(second_embedder.calls, [])
        self.assertTrue(all(chunk["embedding"] is None for chunk in reused_chunks))

    def test_configuration_validates_threshold_and_round_budget(self):
        environment = {
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USERNAME": "neo4j",
            "NEO4J_PASSWORD": "secret",
            "OPENAI_API_KEY": "key",
            "OPS_MIN_SEMANTIC_SCORE": "0.4",
            "OPS_MAX_AGENT_ROUNDS": "6",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = AppConfig.from_env()
        self.assertEqual(config.minimum_semantic_score, 0.4)
        self.assertEqual(config.max_agent_rounds, 6)
        self.assertEqual(config.agent_model, "gpt-5.6-luna")

        with patch.dict(os.environ, environment | {"OPS_MAX_AGENT_ROUNDS": "10"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "between 2 and 8"):
                AppConfig.from_env()

    def test_embedding_adapter_preserves_api_order(self):
        response = SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.3, 0.4]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2]),
            ]
        )
        endpoint = SimpleNamespace(create=lambda **_: response)
        embedder = OpenAIEmbedder(SimpleNamespace(embeddings=endpoint), "model", 2)
        self.assertEqual(
            embedder.embed_documents(["one", "two"]),
            [[0.1, 0.2], [0.3, 0.4]],
        )

    def test_embedding_dimension_mismatch_is_rejected(self):
        response = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1])])
        embedder = OpenAIEmbedder(
            SimpleNamespace(embeddings=SimpleNamespace(create=lambda **_: response)),
            "model",
            2,
        )
        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            embedder.embed_query("test")


if __name__ == "__main__":
    unittest.main()
