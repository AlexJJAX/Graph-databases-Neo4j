# Operations graph domain

## Platform boundary

Project 3 uses `3-Agentic-Temporal-Incident-Response-Copilot/data/platform.json`, a synthetic Northstar Commerce fixture rather than a live incident index. It contains 9 services, 4 owning teams, 7 deployments with commits, 4 incidents, 9 alerts, 4 runbooks, 3 historical postmortems, and 18 deterministic document chunks. `corpus.py` validates IDs, references, timestamps, service/deployment links, and document sections before graph writes.

## Graph model

The `Ops*` labels isolate this project from the movie and research graphs:

```text
(:OpsService)-[:DEPENDS_ON {criticality}]->(:OpsService)
(:OpsService)-[:OWNED_BY]->(:OpsTeam)
(:OpsDeployment)-[:DEPLOYED_TO]->(:OpsService)
(:OpsDeployment)-[:BUILT_FROM]->(:OpsCommit)
(:OpsIncident)-[:PRECEDED_BY]->(:OpsDeployment)
(:OpsIncident)-[:IMPACTED]->(:OpsService)
(:OpsAlert)-[:TRIGGERED_FOR]->(:OpsService)
(:OpsAlert)-[:SIGNALS]->(:OpsIncident)
(:OpsRunbook)-[:APPLIES_TO]->(:OpsService)
(:OpsRunbook)-[:HAS_OPS_CHUNK]->(:OpsChunk {embedding})
(:OpsPostmortem)-[:DOCUMENTS]->(:OpsIncident)
(:OpsPostmortem)-[:HAS_OPS_CHUNK]->(:OpsChunk {embedding})
```

Operational timestamps are stored as Neo4j zoned datetimes normalized to UTC. Temporal adjacency—such as a deployment preceding an incident—is evidence for investigation, not proof of causation. Likewise, dependency paths describe plausible exposure; observed impact comes from incident and alert evidence.

## Search and ingestion

`graph_store.py` creates unique constraints for merge identifiers, temporal indexes for deployments/incidents/alerts, a service-name text index, the 1,536-dimensional cosine vector index `ops_chunk_embedding`, and `ops_chunk_fulltext` over chunk text, title, and section. `ingest.py --dry-run` validates without Neo4j/OpenAI. Normal ingestion waits for indexes, hashes chunks, embeds only changed or missing vectors, upserts relationships, and reports reused embeddings.

`retrieval.py` searches runbook and postmortem chunks with `HybridCypherRetriever`: sanitized Lucene text and embeddings are combined with a 65/35 linear vector/full-text ranking, optionally filtered by services/source type, deduplicated, and rejected below `OPS_MIN_SEMANTIC_SCORE` (default `0.22`). Results are expanded to their document, incident, and connected services.

Source anchors: `data/platform.json`, `corpus.py`, `graph_store.py`, `retrieval.py`, and `config.py`.