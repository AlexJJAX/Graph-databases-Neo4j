from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from chunking import load_corpus  # noqa: E402
from embeddings import OpenAI2Embedder  # noqa: E402
from ingest import prepare_rows  # noqa: E402


class FakeEmbeddingsEndpoint:
    def __init__(self, dimensions: int, *, wrong_dimensions: bool = False):
        self.calls: list[dict] = []
        self.dimensions = dimensions
        self.wrong_dimensions = wrong_dimensions

    def create(self, **kwargs):
        self.calls.append(kwargs)
        size = self.dimensions - 1 if self.wrong_dimensions else self.dimensions
        data = [
            SimpleNamespace(index=index, embedding=[float(index)] * size)
            for index, _ in reversed(list(enumerate(kwargs["input"])))
        ]
        return SimpleNamespace(data=data)


class RecordingEmbedder:
    def __init__(self):
        self.texts: list[str] = []
        self.batch_size: int | None = None

    def embed_documents(self, texts, *, batch_size):
        self.texts = list(texts)
        self.batch_size = batch_size
        return [[float(index), 0.5] for index, _ in enumerate(self.texts)]


class EmbeddingAndIngestTests(unittest.TestCase):
    def test_adapter_preserves_provider_order_across_batches(self):
        endpoint = FakeEmbeddingsEndpoint(3)
        client = SimpleNamespace(embeddings=endpoint)
        embedder = OpenAI2Embedder(client, "embedding-model", 3)

        vectors = embedder.embed_documents(["a", "b", "c"], batch_size=2)

        self.assertEqual(vectors, [[0.0] * 3, [1.0] * 3, [0.0] * 3])
        self.assertEqual(len(endpoint.calls), 2)
        self.assertEqual(endpoint.calls[0]["dimensions"], 3)
        self.assertEqual(endpoint.calls[0]["encoding_format"], "float")

    def test_adapter_rejects_dimension_mismatch(self):
        endpoint = FakeEmbeddingsEndpoint(3, wrong_dimensions=True)
        embedder = OpenAI2Embedder(SimpleNamespace(embeddings=endpoint), "model", 3)

        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            embedder.embed_query("query")

    def test_empty_embedding_batch_skips_provider(self):
        endpoint = FakeEmbeddingsEndpoint(3)
        embedder = OpenAI2Embedder(SimpleNamespace(embeddings=endpoint), "model", 3)

        self.assertEqual(embedder.embed_documents([]), [])
        self.assertEqual(endpoint.calls, [])

    def test_prepare_rows_embeds_only_new_or_changed_chunks(self):
        papers = load_corpus(PROJECT_DIR / "data" / "papers.json")[:1]
        initial_embedder = RecordingEmbedder()
        initial_rows, total, embedded = prepare_rows(
            papers, {}, initial_embedder, batch_size=7
        )
        existing = {
            chunk["chunkId"]: {
                "contentHash": chunk["contentHash"],
                "hasEmbedding": True,
            }
            for chunk in initial_rows[0]["chunks"]
        }
        reuse_embedder = RecordingEmbedder()

        reused_rows, reused_total, reembedded = prepare_rows(
            papers, existing, reuse_embedder, batch_size=7
        )

        self.assertEqual((total, embedded), (3, 3))
        self.assertEqual((reused_total, reembedded), (3, 0))
        self.assertEqual(reuse_embedder.texts, [])
        self.assertTrue(
            all(chunk["embedding"] is None for chunk in reused_rows[0]["chunks"])
        )


if __name__ == "__main__":
    unittest.main()
