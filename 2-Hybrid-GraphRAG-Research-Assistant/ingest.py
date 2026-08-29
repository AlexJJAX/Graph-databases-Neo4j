"""Idempotently ingest and embed the curated AI research corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from chunking import build_chunks, corpus_hash, load_corpus
from config import AppConfig, ConfigurationError, PROJECT_DIR
from embeddings import OpenAI2Embedder
from graph_store import ResearchGraphStore


DEFAULT_CORPUS = PROJECT_DIR / "data" / "papers.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chunk, embed, and ingest the Project 2 research corpus."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and chunk the corpus without contacting Neo4j or OpenAI.",
    )
    return parser


def prepare_rows(
    papers: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    embedder: OpenAI2Embedder,
    *,
    batch_size: int,
) -> tuple[list[dict[str, Any]], int, int]:
    paper_chunks = [(paper, build_chunks(paper)) for paper in papers]
    to_embed = [
        chunk
        for _, chunks in paper_chunks
        for chunk in chunks
        if existing.get(chunk.chunk_id, {}).get("contentHash") != chunk.content_hash
        or not existing.get(chunk.chunk_id, {}).get("hasEmbedding", False)
    ]
    vectors = embedder.embed_documents(
        [chunk.embedding_text for chunk in to_embed],
        batch_size=batch_size,
    )
    vector_by_chunk = {
        chunk.chunk_id: vector for chunk, vector in zip(to_embed, vectors, strict=True)
    }

    rows: list[dict[str, Any]] = []
    total_chunks = 0
    for paper, chunks in paper_chunks:
        total_chunks += len(chunks)
        rows.append(
            {
                **{key: value for key, value in paper.items() if key != "sections"},
                "contentHash": corpus_hash(paper, chunks),
                "chunkIds": [chunk.chunk_id for chunk in chunks],
                "chunks": [
                    {
                        "chunkId": chunk.chunk_id,
                        "section": chunk.section,
                        "sequence": chunk.sequence,
                        "text": chunk.text,
                        "contentHash": chunk.content_hash,
                        "embedding": vector_by_chunk.get(chunk.chunk_id),
                    }
                    for chunk in chunks
                ],
            }
        )
    return rows, total_chunks, len(to_embed)


def main() -> int:
    args = build_parser().parse_args()
    try:
        papers = load_corpus(args.corpus)
        chunk_count = sum(len(build_chunks(paper)) for paper in papers)
        if args.dry_run:
            print(f"Corpus valid: {len(papers)} papers, {chunk_count} chunks.")
            return 0

        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        embedder = OpenAI2Embedder(
            client,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
        )
        with ResearchGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            graph.create_schema()
            graph.wait_for_search_indexes()
            rows, total_chunks, embedded_chunks = prepare_rows(
                papers,
                graph.existing_chunk_state(),
                embedder,
                batch_size=args.batch_size,
            )
            processed = graph.upsert_papers(rows, config.embedding_model)
            graph.upsert_citations(rows)
            stats = graph.stats()

        reused = total_chunks - embedded_chunks
        print(
            f"Ingested {processed} papers and {total_chunks} chunks "
            f"({embedded_chunks} embedded, {reused} reused)."
        )
        print(
            "Graph totals: "
            f"{stats['paperCount']} papers, {stats['chunkCount']} chunks, "
            f"{stats['topicCount']} topics, {stats['citationCount']} citations."
        )
        return 0
    except (
        ConfigurationError,
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
