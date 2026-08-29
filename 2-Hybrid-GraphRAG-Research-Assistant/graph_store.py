"""Neo4j schema, ingestion, and corpus metadata operations."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from neo4j import GraphDatabase, RoutingControl

from config import (
    EMBEDDING_DIMENSIONS,
    FULLTEXT_INDEX_NAME,
    VECTOR_INDEX_NAME,
    Neo4jConfig,
)


SCHEMA_QUERIES = (
    "CYPHER 25 CREATE CONSTRAINT research_paper_id_unique IF NOT EXISTS "
    "FOR (paper:ResearchPaper) REQUIRE paper.paperId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT research_chunk_id_unique IF NOT EXISTS "
    "FOR (chunk:ResearchChunk) REQUIRE chunk.chunkId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT research_author_name_unique IF NOT EXISTS "
    "FOR (author:ResearchAuthor) REQUIRE author.name IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT research_topic_name_unique IF NOT EXISTS "
    "FOR (topic:ResearchTopic) REQUIRE topic.name IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT research_method_name_unique IF NOT EXISTS "
    "FOR (method:ResearchMethod) REQUIRE method.name IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT research_dataset_name_unique IF NOT EXISTS "
    "FOR (dataset:ResearchDataset) REQUIRE dataset.name IS UNIQUE",
    "CYPHER 25 CREATE INDEX research_paper_year_idx IF NOT EXISTS "
    "FOR (paper:ResearchPaper) ON (paper.year)",
    "CYPHER 25 CREATE TEXT INDEX research_paper_title_idx IF NOT EXISTS "
    "FOR (paper:ResearchPaper) ON (paper.title)",
    f"CYPHER 25 CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
    "FOR (chunk:ResearchChunk) ON (chunk.embedding) "
    "OPTIONS {indexConfig: {"
    f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}, "
    "`vector.similarity_function`: 'cosine'}}",
    f"CYPHER 25 CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS "
    "FOR (chunk:ResearchChunk) ON EACH [chunk.text, chunk.section]",
)


UPSERT_PAPERS_QUERY = """
CYPHER 25
UNWIND $papers AS row
MERGE (paper:ResearchPaper {paperId: row.paperId})
SET paper.title = row.title,
    paper.year = row.year,
    paper.abstract = row.abstract,
    paper.sourceUrl = row.sourceUrl,
    paper.contentHash = row.contentHash,
    paper.updatedAt = datetime()
CALL (paper, row) {
  MATCH (paper)-[:HAS_CHUNK]->(stale:ResearchChunk)
  WHERE NOT stale.chunkId IN row.chunkIds
  DETACH DELETE stale
}
CALL (paper) {
  MATCH (:ResearchAuthor)-[relationship:AUTHORED]->(paper)
  DELETE relationship
}
CALL (paper) {
  MATCH (paper)-[relationship:ABOUT]->(:ResearchTopic)
  DELETE relationship
}
CALL (paper) {
  MATCH (paper)-[relationship:USES_METHOD]->(:ResearchMethod)
  DELETE relationship
}
CALL (paper) {
  MATCH (paper)-[relationship:EVALUATED_ON]->(:ResearchDataset)
  DELETE relationship
}
FOREACH (authorName IN row.authors |
  MERGE (author:ResearchAuthor {name: authorName})
  MERGE (author)-[:AUTHORED]->(paper)
)
FOREACH (topicName IN row.topics |
  MERGE (topic:ResearchTopic {name: topicName})
  MERGE (paper)-[:ABOUT]->(topic)
)
FOREACH (methodName IN row.methods |
  MERGE (method:ResearchMethod {name: methodName})
  MERGE (paper)-[:USES_METHOD]->(method)
)
FOREACH (datasetName IN row.datasets |
  MERGE (dataset:ResearchDataset {name: datasetName})
  MERGE (paper)-[:EVALUATED_ON]->(dataset)
)
FOREACH (chunkRow IN row.chunks |
  MERGE (chunk:ResearchChunk {chunkId: chunkRow.chunkId})
  SET chunk.paperId = row.paperId,
      chunk.section = chunkRow.section,
      chunk.sequence = chunkRow.sequence,
      chunk.text = chunkRow.text,
      chunk.contentHash = chunkRow.contentHash
  FOREACH (_ IN CASE WHEN chunkRow.embedding IS NULL THEN [] ELSE [1] END |
    SET chunk.embedding = chunkRow.embedding,
        chunk.embeddingModel = $embeddingModel
  )
  MERGE (paper)-[:HAS_CHUNK]->(chunk)
)
RETURN count(DISTINCT paper) AS papersProcessed
""".strip()


UPSERT_CITATIONS_QUERY = """
CYPHER 25
UNWIND $papers AS row
MATCH (paper:ResearchPaper {paperId: row.paperId})
CALL (paper) {
  MATCH (paper)-[relationship:CITES]->(:ResearchPaper)
  DELETE relationship
}
FOREACH (citedPaperId IN row.cites |
  MERGE (cited:ResearchPaper {paperId: citedPaperId})
  MERGE (paper)-[:CITES]->(cited)
)
RETURN count(DISTINCT paper) AS papersProcessed
""".strip()


class ResearchGraphStore:
    """Own one Neo4j driver and isolate all Project 2 graph operations."""

    def __init__(self, config: Neo4jConfig):
        self.database = config.database
        self.driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )

    def __enter__(self) -> "ResearchGraphStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def create_schema(self) -> None:
        for query in SCHEMA_QUERIES:
            self.driver.execute_query(query, database_=self.database)

    def wait_for_search_indexes(self, timeout_seconds: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            states = self.index_states()
            if states.get(VECTOR_INDEX_NAME) == "ONLINE" and states.get(
                FULLTEXT_INDEX_NAME
            ) == "ONLINE":
                return
            time.sleep(0.5)
        raise TimeoutError("Research vector/full-text indexes did not become ONLINE")

    def index_states(self) -> dict[str, str]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 SHOW INDEXES YIELD name, state "
            "WHERE name IN $names RETURN name, state LIMIT 10",
            names=[VECTOR_INDEX_NAME, FULLTEXT_INDEX_NAME],
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {record["name"]: record["state"] for record in records}

    def is_ready(self) -> bool:
        states = self.index_states()
        return (
            states.get(VECTOR_INDEX_NAME) == "ONLINE"
            and states.get(FULLTEXT_INDEX_NAME) == "ONLINE"
            and self.stats()["chunkCount"] > 0
        )

    def existing_chunk_state(self) -> dict[str, dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (chunk:ResearchChunk) "
            "RETURN chunk.chunkId AS chunkId, chunk.contentHash AS contentHash, "
            "chunk.embedding IS NOT NULL AS hasEmbedding LIMIT 10000",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return {
            record["chunkId"]: {
                "contentHash": record["contentHash"],
                "hasEmbedding": record["hasEmbedding"],
            }
            for record in records
        }

    def upsert_papers(
        self, papers: Sequence[Mapping[str, Any]], embedding_model: str
    ) -> int:
        records, _, _ = self.driver.execute_query(
            UPSERT_PAPERS_QUERY,
            papers=[dict(paper) for paper in papers],
            embeddingModel=embedding_model,
            database_=self.database,
        )
        return int(records[0]["papersProcessed"])

    def upsert_citations(self, papers: Sequence[Mapping[str, Any]]) -> int:
        records, _, _ = self.driver.execute_query(
            UPSERT_CITATIONS_QUERY,
            papers=[{"paperId": p["paperId"], "cites": p["cites"]} for p in papers],
            database_=self.database,
        )
        return int(records[0]["papersProcessed"])

    def stats(self) -> dict[str, int]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 "
            "CALL () { MATCH (paper:ResearchPaper) RETURN count(paper) AS paperCount } "
            "CALL () { MATCH (chunk:ResearchChunk) RETURN count(chunk) AS chunkCount } "
            "CALL () { MATCH (topic:ResearchTopic) RETURN count(topic) AS topicCount } "
            "CALL () { MATCH (:ResearchPaper)-[citation:CITES]->(:ResearchPaper) "
            "RETURN count(citation) AS citationCount } "
            "RETURN paperCount, chunkCount, topicCount, citationCount LIMIT 1",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        if not records:
            return {"paperCount": 0, "chunkCount": 0, "topicCount": 0, "citationCount": 0}
        return {key: int(records[0][key]) for key in records[0].keys()}

    def topics(self) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            "CYPHER 25 MATCH (paper:ResearchPaper)-[:ABOUT]->(topic:ResearchTopic) "
            "RETURN topic.name AS name, count(paper) AS paperCount "
            "ORDER BY paperCount DESC, name LIMIT 50",
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in records]
