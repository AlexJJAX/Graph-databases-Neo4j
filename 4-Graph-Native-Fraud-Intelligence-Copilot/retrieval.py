"""Hybrid vector/full-text retrieval with fraud-graph expansion."""

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
MATCH (document:FraudDocument)-[:HAS_FRAUD_CHUNK]->(node)
OPTIONAL MATCH (document)-[:REFERENCES_ACCOUNT]->(account:FraudAccount)
OPTIONAL MATCH (document)-[:REFERENCES_DEVICE]->(device:FraudDevice)
OPTIONAL MATCH (document)-[:REFERENCES_MERCHANT]->(merchant:FraudMerchant)
WITH node, score, document,
     collect(DISTINCT account.accountId) AS accountIds,
     collect(DISTINCT device.deviceId) AS deviceIds,
     collect(DISTINCT merchant.merchantId) AS merchantIds
WHERE (size($sourceTypes) = 0 OR document.documentType IN $sourceTypes)
  AND (size($accountIds) = 0 OR document.documentType IN ['typology', 'policy']
       OR any(id IN accountIds WHERE id IN $accountIds))
RETURN node.chunkId AS chunkId, node.text AS text, node.section AS section,
       node.title AS title, document.documentId AS documentId,
       document.documentType AS sourceType, accountIds, deviceIds, merchantIds,
       score AS hybridScore,
       vector.similarity.cosine(node.embedding, $queryVector) AS semanticScore
""".strip()


LUCENE_SPECIAL_CHARS = re.compile(r"[+\-&|!(){}\[\]^\"~*?:\\/]")


def sanitize_fulltext_query(question: str) -> str:
    cleaned = LUCENE_SPECIAL_CHARS.sub(" ", question)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "fraud investigation transaction network"


def format_fraud_record(record: Record) -> RetrieverResultItem:
    return RetrieverResultItem(content=record["text"], metadata=record.data())


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    evidence: tuple[EvidenceRecord, ...]
    elapsed_ms: int


class FraudEvidenceRetriever:
    def __init__(
        self, *, driver: Any, database: str, embedder: Any,
        minimum_semantic_score: float = 0.24, backend: Any | None = None,
    ):
        self._embedder = embedder
        self._minimum_semantic_score = minimum_semantic_score
        self._backend = backend or HybridCypherRetriever(
            driver=driver,
            vector_index_name=VECTOR_INDEX_NAME,
            fulltext_index_name=FULLTEXT_INDEX_NAME,
            retrieval_query=RETRIEVAL_QUERY,
            embedder=embedder,
            result_formatter=format_fraud_record,
            neo4j_database=database,
        )

    def search(
        self, query: str, *, account_ids: list[str] | None = None,
        source_types: list[str] | None = None, top_k: int = 5,
    ) -> RetrievalResult:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        account_ids = list(dict.fromkeys(account_ids or []))[:12]
        allowed = {"typology", "policy", "case_report"}
        source_types = list(dict.fromkeys(source_types or []))
        if any(item not in allowed for item in source_types):
            raise ValueError("source_types may contain typology, policy, or case_report")
        top_k = max(1, min(int(top_k), 8))
        started = time.perf_counter()
        query_vector = self._embedder.embed_query(query)
        result = self._backend.search(
            query_text=sanitize_fulltext_query(query), query_vector=query_vector,
            top_k=min(top_k * 3, 24), effective_search_ratio=2,
            query_params={"accountIds": account_ids, "sourceTypes": source_types, "queryVector": query_vector},
            ranker="linear", alpha=0.65,
        )
        evidence: list[EvidenceRecord] = []
        seen: set[str] = set()
        for item in result.items:
            metadata = dict(item.metadata or {})
            chunk_id = str(metadata.get("chunkId") or "")
            semantic_score = float(metadata.get("semanticScore") or 0.0)
            if not chunk_id or chunk_id in seen or semantic_score < self._minimum_semantic_score:
                continue
            seen.add(chunk_id)
            evidence.append(EvidenceRecord(
                evidence_id="", kind="document", source_id=chunk_id,
                title=f"{metadata.get('title')} · {metadata.get('section')}",
                content=str(metadata.get("text") or ""),
                source_type=str(metadata.get("sourceType") or "document"),
                score=semantic_score,
                metadata={
                    "document_id": metadata.get("documentId"),
                    "account_ids": metadata.get("accountIds") or [],
                    "device_ids": metadata.get("deviceIds") or [],
                    "merchant_ids": metadata.get("merchantIds") or [],
                    "hybrid_score": round(float(metadata.get("hybridScore") or 0.0), 4),
                },
            ))
            if len(evidence) >= top_k:
                break
        return RetrievalResult(tuple(evidence), int((time.perf_counter() - started) * 1000))
