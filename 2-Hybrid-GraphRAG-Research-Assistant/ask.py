"""CLI companion for testing the Project 2 assistant without a browser."""

from __future__ import annotations

import argparse
import sys

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError
from graph_store import ResearchGraphStore
from retrieval import SearchFilters
from runtime import build_assistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask the AI research graph.")
    parser.add_argument("question")
    parser.add_argument("--topic")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        filters = SearchFilters(args.topic, args.year_from, args.year_to)
        with ResearchGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            result = build_assistant(config, graph, client).ask(
                args.question,
                top_k=args.top_k,
                filters=filters,
            )
        print(f"\n{result.answer}\n")
        print("Evidence")
        for item in result.evidence:
            print(
                f"[{item.evidence_id}] {item.title} ({item.year}) · {item.section} "
                f"· semantic {item.semantic_score:.3f}"
            )
            print(f"    {item.source_url}")
        print(
            f"\nRetrieved in {result.metrics['retrieval_ms']} ms; "
            f"generated in {result.metrics['generation_ms']} ms."
        )
        return 0
    except (
        ConfigurationError,
        DriverError,
        Neo4jError,
        OpenAIError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
