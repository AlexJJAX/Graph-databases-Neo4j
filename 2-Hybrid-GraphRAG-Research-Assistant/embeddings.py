"""OpenAI 2.x embedding adapter for neo4j-graphrag."""

from __future__ import annotations

from typing import Any, Sequence

from neo4j_graphrag.embeddings.base import Embedder


class OpenAI2Embedder(Embedder):
    """Bridge the current OpenAI SDK to neo4j-graphrag's Embedder protocol."""

    def __init__(self, client: Any, model: str, dimensions: int):
        super().__init__()
        self._client = client
        self.model = model
        self.dimensions = dimensions

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(
        self, texts: Sequence[str], *, batch_size: int = 64
    ) -> list[list[float]]:
        if not texts:
            return []
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            response = self._client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            for item in ordered:
                vector = list(item.embedding)
                if len(vector) != self.dimensions:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {self.dimensions}, "
                        f"received {len(vector)}"
                    )
                embeddings.append(vector)
        return embeddings
