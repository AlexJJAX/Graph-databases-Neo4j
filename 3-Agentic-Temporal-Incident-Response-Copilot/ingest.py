"""Idempotently ingest the synthetic operational topology and evidence corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError, PROJECT_DIR
from corpus import CorpusError, build_document_rows, load_platform
from embeddings import OpenAIEmbedder
from graph_store import OperationsGraphStore


DEFAULT_CORPUS = PROJECT_DIR / "data" / "platform.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest the Project 3 operational graph and document vectors."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count the corpus without contacting Neo4j or OpenAI.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = load_platform(args.corpus)
        chunk_count = sum(
            len(document["sections"])
            for collection in (payload["runbooks"], payload["postmortems"])
            for document in collection
        )
        if args.dry_run:
            print(
                "Corpus valid: "
                f"{len(payload['services'])} services, "
                f"{len(payload['incidents'])} incidents, "
                f"{len(payload['deployments'])} deployments, "
                f"{chunk_count} document chunks."
            )
            return 0

        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        embedder = OpenAIEmbedder(
            client,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
        )
        with OperationsGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            graph.create_schema()
            graph.wait_for_search_indexes()
            runbooks, postmortems, chunks, total_chunks, embedded_chunks = (
                build_document_rows(
                    payload,
                    graph.existing_chunk_state(),
                    embedder,
                    batch_size=args.batch_size,
                )
            )
            graph.ingest(
                payload,
                runbooks,
                postmortems,
                chunks,
                config.embedding_model,
            )
            stats = graph.stats()

        print(
            f"Ingested {stats['serviceCount']} services, {stats['incidentCount']} incidents, "
            f"and {total_chunks} chunks "
            f"({embedded_chunks} embedded, {total_chunks - embedded_chunks} reused)."
        )
        print(
            "Graph totals: "
            f"{stats['deploymentCount']} deployments, {stats['alertCount']} alerts, "
            f"{stats['chunkCount']} evidence chunks."
        )
        return 0
    except (
        ConfigurationError,
        CorpusError,
        DriverError,
        Neo4jError,
        OpenAIError,
        OSError,
        TimeoutError,
        ValueError,
    ) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
