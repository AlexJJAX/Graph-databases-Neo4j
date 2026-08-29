"""Hybrid vector/full-text retrieval followed by knowledge-graph expansion."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from neo4j import Record
from neo4j_graphrag.retrievers import HybridCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from config import FULLTEXT_INDEX_NAME, VECTOR_INDEX_NAME


RETRIEVAL_QUERY = """
MATCH (paper:ResearchPaper)-[:HAS_CHUNK]->(node)
WHERE ($yearFrom IS NULL OR paper.year >= $yearFrom)
  AND ($yearTo IS NULL OR paper.year <= $yearTo)
  AND ($topic IS NULL OR EXISTS {
        MATCH (paper)-[:ABOUT]->(requestedTopic:ResearchTopic {name: $topic})
      })
RETURN node.chunkId AS chunkId,
       node.text AS text,
       node.section AS section,
       paper.paperId AS paperId,
       paper.title AS title,
       paper.year AS year,
       paper.abstract AS abstract,
       paper.sourceUrl AS sourceUrl,
       COLLECT {
         MATCH (author:ResearchAuthor)-[:AUTHORED]->(paper)
         RETURN author.name ORDER BY author.name
       } AS authors,
       COLLECT {
         MATCH (paper)-[:ABOUT]->(topic:ResearchTopic)
         RETURN topic.name ORDER BY topic.name
       } AS topics,
       COLLECT {
         MATCH (paper)-[:USES_METHOD]->(method:ResearchMethod)
         RETURN method.name ORDER BY method.name
       } AS methods,
       COLLECT {
         MATCH (paper)-[:EVALUATED_ON]->(dataset:ResearchDataset)
         RETURN dataset.name ORDER BY dataset.name
       } AS datasets,
       COLLECT {
         MATCH (paper)-[:CITES]->(cited:ResearchPaper)
         RETURN {paperId: cited.paperId, title: cited.title}
         ORDER BY cited.year, cited.title LIMIT 6
       } AS citedPapers,
       COLLECT {
         MATCH (citing:ResearchPaper)-[:CITES]->(paper)
         RETURN {paperId: citing.paperId, title: citing.title}
         ORDER BY citing.year, citing.title LIMIT 6
       } AS citedBy,
       score AS hybridScore,
       vector.similarity.cosine(node.embedding, $query_vector) AS semanticScore
""".strip()


LUCENE_SPECIAL_CHARS = re.compile(r"[+\-&|!(){}\[\]^\"~*?:\\/]")


@dataclass(frozen=True, slots=True)
class SearchFilters:
    topic: str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def __post_init__(self) -> None:
        if self.year_from is not None and not 1900 <= self.year_from <= 2100:
            raise ValueError("year_from must be between 1900 and 2100")
        if self.year_to is not None and not 1900 <= self.year_to <= 2100:
            raise ValueError("year_to must be between 1900 and 2100")
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from cannot be later than year_to")

    def as_query_params(self) -> dict[str, Any]:
        return {
            "topic": self.topic.strip() if self.topic and self.topic.strip() else None,
            "yearFrom": self.year_from,
            "yearTo": self.year_to,
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    chunk_id: str
    paper_id: str
    title: str
    year: int
    section: str
    text: str
    abstract: str
    source_url: str
    authors: tuple[str, ...]
    topics: tuple[str, ...]
    methods: tuple[str, ...]
    datasets: tuple[str, ...]
    cited_papers: tuple[dict[str, str], ...]
    cited_by: tuple[dict[str, str], ...]
    hybrid_score: float
    semantic_score: float

    @classmethod
    def from_metadata(cls, evidence_id: str, metadata: dict[str, Any]) -> "Evidence":
        return cls(
            evidence_id=evidence_id,
            chunk_id=str(metadata["chunkId"]),
            paper_id=str(metadata["paperId"]),
            title=str(metadata["title"]),
            year=int(metadata["year"]),
            section=str(metadata["section"]),
            text=str(metadata["text"]),
            abstract=str(metadata.get("abstract") or ""),
            source_url=str(metadata["sourceUrl"]),
            authors=tuple(metadata.get("authors") or ()),
            topics=tuple(metadata.get("topics") or ()),
            methods=tuple(metadata.get("methods") or ()),
            datasets=tuple(metadata.get("datasets") or ()),
            cited_papers=tuple(metadata.get("citedPapers") or ()),
            cited_by=tuple(metadata.get("citedBy") or ()),
            hybrid_score=float(metadata.get("hybridScore") or 0.0),
            semantic_score=float(metadata.get("semanticScore") or 0.0),
        )

    def as_context(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "paper_id": self.paper_id,
            "title": self.title,
            "year": self.year,
            "section": self.section,
            "text": self.text,
            "authors": list(self.authors),
            "topics": list(self.topics),
            "methods": list(self.methods),
            "datasets": list(self.datasets),
            "cites": list(self.cited_papers),
            "cited_by": list(self.cited_by),
        }

    def as_dict(self) -> dict[str, Any]:
        value = self.as_context()
        value.update(
            {
                "chunk_id": self.chunk_id,
                "abstract": self.abstract,
                "source_url": self.source_url,
                "hybrid_score": round(self.hybrid_score, 4),
                "semantic_score": round(self.semantic_score, 4),
            }
        )
        return value


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    evidence: tuple[Evidence, ...]
    elapsed_ms: int


def sanitize_fulltext_query(question: str) -> str:
    cleaned = LUCENE_SPECIAL_CHARS.sub(" ", question)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "artificial intelligence research"


def format_research_record(record: Record) -> RetrieverResultItem:
    return RetrieverResultItem(content=record["text"], metadata=record.data())


class ResearchRetriever:
    def __init__(
        self,
        *,
        driver: Any,
        database: str,
        embedder: Any,
        minimum_semantic_score: float = 0.25,
        backend: Any | None = None,
    ):
        self._embedder = embedder
        self._minimum_semantic_score = minimum_semantic_score
        self._backend = backend or HybridCypherRetriever(
            driver=driver,
            vector_index_name=VECTOR_INDEX_NAME,
            fulltext_index_name=FULLTEXT_INDEX_NAME,
            retrieval_query=RETRIEVAL_QUERY,
            embedder=embedder,
            result_formatter=format_research_record,
            neo4j_database=database,
        )

    def search(
        self,
        question: str,
        *,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        question = question.strip()
        if not question:
            raise ValueError("Question cannot be empty")
        top_k = max(1, min(int(top_k), 8))
        filters = filters or SearchFilters()

        started = time.perf_counter()
        query_vector = self._embedder.embed_query(question)
        candidate_count = min(top_k * 3, 24)
        result = self._backend.search(
            query_text=sanitize_fulltext_query(question),
            query_vector=query_vector,
            top_k=candidate_count,
            effective_search_ratio=2,
            query_params=filters.as_query_params(),
            ranker="linear",
            alpha=0.65,
        )

        evidence: list[Evidence] = []
        seen_chunks: set[str] = set()
        for item in result.items:
            metadata = dict(item.metadata or {})
            chunk_id = str(metadata.get("chunkId") or "")
            semantic_score = float(metadata.get("semanticScore") or 0.0)
            if not chunk_id or chunk_id in seen_chunks:
                continue
            if semantic_score < self._minimum_semantic_score:
                continue
            seen_chunks.add(chunk_id)
            evidence.append(Evidence.from_metadata(f"R{len(evidence) + 1}", metadata))
            if len(evidence) >= top_k:
                break

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return RetrievalResult(evidence=tuple(evidence), elapsed_ms=elapsed_ms)
