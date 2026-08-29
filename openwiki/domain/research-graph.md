# Research graph domain

## Corpus boundary

Project 2 uses `2-Hybrid-GraphRAG-Research-Assistant/data/papers.json`, a hand-curated corpus of eight concise AI-literature summaries with stable arXiv URLs. The records cover Attention, BERT, DPR, RAG, ReAct, Toolformer, Lost in the Middle, and GraphRAG. This is portfolio data, not a live scholarly index or a copy of full papers.

`chunking.py` validates required metadata, unique paper IDs, year bounds, section structure, string-list fields, and citation targets. Section text is normalized and split into deterministic word chunks of at most 140 words with 25-word overlap. IDs include paper, section, and part positions; SHA-256 content hashes make changed chunks detectable.

## Labels and relationships

All labels use the `Research*` prefix to keep this graph isolated from Project 1’s movie graph:

```text
(:ResearchAuthor)-[:AUTHORED]->(:ResearchPaper)
(:ResearchPaper)-[:HAS_CHUNK]->(:ResearchChunk {embedding})
(:ResearchPaper)-[:ABOUT]->(:ResearchTopic)
(:ResearchPaper)-[:USES_METHOD]->(:ResearchMethod)
(:ResearchPaper)-[:EVALUATED_ON]->(:ResearchDataset)
(:ResearchPaper)-[:CITES]->(:ResearchPaper)
```

A paper stores title, year, abstract, source URL, and content hash. Chunks store text, section, sequence, content hash, and an embedding. Retrieval returns these records plus authors, topics, methods, datasets, and incoming/outgoing citation neighbors.

## Schema and ingestion

`graph_store.py` creates unique constraints for paper/chunk IDs and entity names, a paper-year index, a paper-title text index, the 1,536-dimensional cosine vector index `research_chunk_embedding`, and the full-text index `research_chunk_fulltext` over chunk text and section.

`ingest.py --dry-run` validates and chunks without contacting external services. Normal ingestion waits for both search indexes, embeds only chunks whose hash changed or that lack an embedding, upserts papers and metadata relationships, removes stale chunks, refreshes citations, and reports graph totals. Re-running ingestion is therefore intended to be idempotent and incremental.

Source anchors: `2-Hybrid-GraphRAG-Research-Assistant/chunking.py`, `graph_store.py`, `ingest.py`, and `data/papers.json`.