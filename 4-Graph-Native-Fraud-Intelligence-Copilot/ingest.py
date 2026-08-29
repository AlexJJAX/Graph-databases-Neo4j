"""Idempotently ingest the synthetic fraud graph and evidence corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError, PROJECT_DIR
from corpus import CorpusError, build_document_rows, load_fraud_network
from embeddings import OpenAIEmbedder
from graph_store import FraudGraphStore


DEFAULT_CORPUS = PROJECT_DIR / "data" / "fraud_network.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the Project 4 fraud graph and document vectors.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true", help="Validate the corpus without contacting Neo4j or OpenAI.")
    args = parser.parse_args()
    try:
        payload = load_fraud_network(args.corpus)
        chunk_count = sum(len(item["sections"]) for item in payload["documents"])
        if args.dry_run:
            print(f"Corpus valid: {len(payload['persons'])} persons, {len(payload['accounts'])} accounts, {len(payload['transactions'])} transactions, {len(payload['alerts'])} alerts, {chunk_count} document chunks.")
            return 0
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        embedder = OpenAIEmbedder(client, config.embedding_model, config.embedding_dimensions)
        with FraudGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            graph.create_schema()
            graph.wait_for_search_indexes()
            documents, chunks, total_chunks, embedded_chunks = build_document_rows(payload, graph.existing_chunk_state(), embedder, batch_size=args.batch_size)
            graph.ingest(payload, documents, chunks, config.embedding_model)
            stats = graph.stats()
        print(f"Ingested {stats['personCount']} persons, {stats['accountCount']} accounts, {stats['transactionCount']} transactions, and {total_chunks} chunks ({embedded_chunks} embedded, {total_chunks - embedded_chunks} reused).")
        print(f"Graph totals: {stats['alertCount']} alerts, {stats['caseCount']} cases, {stats['chunkCount']} grounded chunks.")
        return 0
    except (ConfigurationError, CorpusError, DriverError, Neo4jError, OpenAIError, OSError, TimeoutError, ValueError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
