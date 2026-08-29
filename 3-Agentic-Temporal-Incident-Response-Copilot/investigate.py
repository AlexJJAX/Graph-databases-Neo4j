"""CLI companion for incident investigations without the web workbench."""

from __future__ import annotations

import argparse
import sys

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError
from graph_store import OperationsGraphStore
from runtime import build_agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigate the operations graph.")
    parser.add_argument("question")
    parser.add_argument("--show-trace", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        with OperationsGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            result = build_agent(config, graph, client).investigate(args.question)

        print(f"\n{result.report.title}\n")
        print(result.answer)
        print("\nEvidence ledger")
        for record in result.evidence:
            score = f" · semantic {record.score:.3f}" if record.score is not None else ""
            print(f"[{record.evidence_id}] {record.title} · {record.source_type}{score}")
        if args.show_trace:
            print("\nAgent trace")
            for item in result.trace:
                print(
                    f"{item.step}. {item.tool} — {item.status} — "
                    f"{item.summary} ({item.elapsed_ms} ms)"
                )
        print(
            f"\n{result.metrics['tool_calls']} tool calls, "
            f"{result.metrics['evidence_count']} evidence records, "
            f"{result.metrics['total_ms']} ms total."
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
        print(f"Investigation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
