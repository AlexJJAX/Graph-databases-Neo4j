"""Hybrid vector/full-text retrieval with operational graph expansion."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from neo4j import Record
from neo4j_graphrag.retrievers import HybridCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from config import FULLTEXT_INDEX_NAME, VECTOR_INDEX_NAME
from evidence import EvidenceRecord


RETRIEVAL_QUERY = """
MATCH (document)-[:HAS_OPS_CHUNK]->(node)
WHERE document:OpsRunbook OR document:OpsPostmortem
OPTIONAL MATCH (document:OpsRunbook)-[:APPLIES_TO]->(runbookService:OpsService)
OPTIONAL MATCH (document:OpsPostmortem)-[:DOCUMENTS]->(documentedIncident:OpsIncident)
OPTIONAL MATCH (documentedIncident)-[:IMPACTED]->(incidentService:OpsService)
WITH node, score, document, documentedIncident,
     CASE WHEN document:OpsRunbook THEN 'runbook' ELSE 'postmortem' END AS sourceType,
     [serviceId IN
       collect(DISTINCT runbookService.serviceId) +
       collect(DISTINCT incidentService.serviceId)
       WHERE serviceId IS NOT NULL] AS serviceIds
WHERE (size($serviceIds) = 0 OR any(serviceId IN serviceIds WHERE serviceId IN $serviceIds))
  AND (size($sourceTypes) = 0 OR sourceType IN $sourceTypes)
RETURN node.chunkId AS chunkId, node.text AS text, node.section AS section,
       node.title AS title, node.sourceId AS sourceId, sourceType,
       serviceIds,
       CASE WHEN documentedIncident IS NULL THEN null
            ELSE documentedIncident.incidentId END AS incidentId,
       score AS hybridScore,
       vector.similarity.cosine(node.embedding, $queryVector) AS semanticScore
""".strip()


LUCENE_SPECIAL_CHARS = re.compile(r"[+\-&|!(){}\[\]^\"~*?:\\/]")


def sanitize_fulltext_query(question: str) -> str:
    cleaned = LUCENE_SPECIAL_CHARS.sub(" ", question)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "incident response operations"


def format_operational_record(record: Record) -> RetrieverResultItem:
    return RetrieverResultItem(content=record["text"], metadata=record.data())


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    evidence: tuple[EvidenceRecord, ...]
    elapsed_ms: int


class OperationalRetriever:
    def __init__(
        self,
        *,
        driver: Any,
        database: str,
        embedder: Any,
        minimum_semantic_score: float = 0.22,
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
            result_formatter=format_operational_record,
            neo4j_database=database,
        )

    def search(
        self,
        query: str,
        *,
        service_ids: list[str] | None = None,
        source_types: list[str] | None = None,
        top_k: int = 5,
    ) -> RetrievalResult:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        service_ids = list(dict.fromkeys(service_ids or []))[:8]
        allowed_types = {"runbook", "postmortem"}
        source_types = list(dict.fromkeys(source_types or []))
        if any(source_type not in allowed_types for source_type in source_types):
            raise ValueError("source_types may contain runbook or postmortem")
        top_k = max(1, min(int(top_k), 8))

        started = time.perf_counter()
        query_vector = self._embedder.embed_query(query)
        result = self._backend.search(
            query_text=sanitize_fulltext_query(query),
            query_vector=query_vector,
            top_k=min(top_k * 3, 24),
            effective_search_ratio=2,
            query_params={
                "serviceIds": service_ids,
                "sourceTypes": source_types,
                "queryVector": query_vector,
            },
            ranker="linear",
            alpha=0.65,
        )

        evidence: list[EvidenceRecord] = []
        seen: set[str] = set()
        for item in result.items:
            metadata = dict(item.metadata or {})
            chunk_id = str(metadata.get("chunkId") or "")
            semantic_score = float(metadata.get("semanticScore") or 0.0)
            if not chunk_id or chunk_id in seen:
                continue
            if semantic_score < self._minimum_semantic_score:
                continue
            seen.add(chunk_id)
            evidence.append(
                EvidenceRecord(
                    evidence_id="",
                    kind="document",
                    source_id=chunk_id,
                    title=f"{metadata.get('title')} · {metadata.get('section')}",
                    content=str(metadata.get("text") or ""),
                    source_type=str(metadata.get("sourceType") or "document"),
                    score=semantic_score,
                    metadata={
                        "document_id": metadata.get("sourceId"),
                        "incident_id": metadata.get("incidentId"),
                        "service_ids": metadata.get("serviceIds") or [],
                        "hybrid_score": round(
                            float(metadata.get("hybridScore") or 0.0), 4
                        ),
                    },
                )
            )
            if len(evidence) >= top_k:
                break
        return RetrievalResult(
            evidence=tuple(evidence),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
