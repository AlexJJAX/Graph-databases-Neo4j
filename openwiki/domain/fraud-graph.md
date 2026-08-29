# Fraud graph domain

## Platform boundary

Project 4 is a synthetic Northstar Financial fraud-investigation workbench. Its `Fraud*` labels and `fraud_*` indexes isolate the identity, payment, evidence, and investigation-memory graph from Projects 1–3. The corpus contains 10 people and accounts, eight devices, nine masked addresses, eight masked phones, 13 transactions, four merchants, four alerts, two cases, six documents, and 15 deterministic chunks.

## Graph model

```text
(:FraudPerson)-[:CONTROLS]->(:FraudAccount)
(:FraudPerson)-[:USES_DEVICE|USES_PHONE|LIVES_AT]->(:FraudDevice|FraudPhone|FraudAddress)
(:FraudAccount)-[:INITIATED]->(:FraudTransaction)-[:CREDITED]->(:FraudAccount)
(:FraudTransaction)-[:AT_MERCHANT|FROM_DEVICE]->(:FraudMerchant|FraudDevice)
(:FraudAlert)-[:FLAGS_ACCOUNT|FLAGS_TRANSACTION]->(...)
(:FraudCase)-[:CONTAINS_ALERT]->(:FraudAlert)
(:FraudDocument)-[:HAS_FRAUD_CHUNK]->(:FraudChunk {embedding})
(:FraudDocument)-[:REFERENCES_ACCOUNT|REFERENCES_DEVICE|REFERENCES_MERCHANT]->(...)
(:FraudInvestigation)-[:HAS_TURN]->(:FraudTurn)
```

Transactions are nodes because time, amount, channel, device, merchant/counterparty, and alert context belong to the transaction itself. Native Neo4j datetimes are normalized to UTC; embeddings live only on `FraudChunk` nodes. Every `MERGE` identifier has a uniqueness constraint.

## Evidence and retrieval

The graph supports shared-identifier checks, bounded fund-flow tracing, exact three-account cycle detection, merchant-concentration aggregation, alert context, and historical comparison. A shared identifier, graph path, cycle, alert, or similar case is a signal—not proof of common control, intent, or fraud.

`fraud_chunk_embedding` is a 1,536-dimensional cosine index and `fraud_chunk_fulltext` indexes chunk text, title, and section. Hybrid retrieval combines vector and full-text ranking at 65/35, can filter by account and source type, expands chunks to referenced entities, and rejects weak results below `FRAUD_MIN_SEMANTIC_SCORE` (default `0.24`). Ingestion hashes chunks and re-embeds only new, changed, or missing vectors.

Source anchors: `4-Graph-Native-Fraud-Intelligence-Copilot/data/fraud_network.json`, `corpus.py`, `graph_store.py`, `retrieval.py`, and `config.py`.
