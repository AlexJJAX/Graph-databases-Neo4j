"""Agent-route, evidence, and diagnosis evaluation for Project 3."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError, PROJECT_DIR
from graph_store import OperationsGraphStore
from runtime import build_agent


DEFAULT_EVAL_SET = PROJECT_DIR / "evals" / "questions.json"


def score_cases(cases: list[dict[str, Any]], results: list[Any]) -> dict[str, float]:
    route_scores: list[float] = []
    evidence_hits = 0
    diagnosis_hits = 0
    bounded = 0
    for case, result in zip(cases, results, strict=True):
        used_tools = {item.tool for item in result.trace}
        expected_tools = set(case.get("expectedTools", []))
        route_scores.append(
            len(used_tools & expected_tools) / len(expected_tools)
            if expected_tools
            else 1.0
        )
        sources = {record.source_id for record in result.evidence}
        expected_sources = set(case.get("expectedSourceIds", []))
        evidence_hits += int(not expected_sources or bool(sources & expected_sources))
        answer = (
            result.report.summary.claim
            + " "
            + result.report.leading_hypothesis.claim
        ).lower()
        terms = [term.lower() for term in case.get("expectedTerms", [])]
        diagnosis_hits += int(not terms or all(term in answer for term in terms))
        bounded += int(result.metrics["tool_calls"] <= case.get("maxToolCalls", 8))
    count = len(cases)
    return {
        "cases": float(count),
        "tool_route_recall": sum(route_scores) / count if count else 0.0,
        "evidence_source_hit_rate": evidence_hits / count if count else 0.0,
        "diagnosis_term_accuracy": diagnosis_hits / count if count else 0.0,
        "bounded_investigation_rate": bounded / count if count else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the incident agent.")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET)
    args = parser.parse_args()
    try:
        cases = json.loads(args.eval_set.read_text(encoding="utf-8"))
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        with OperationsGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            agent = build_agent(config, graph, client)
            results = []
            for case in cases:
                print(f"{case['id']}: running...", flush=True)
                result = agent.investigate(case["question"])
                results.append(result)
                print(
                    f"{case['id']}: {[item.tool for item in result.trace]} · "
                    f"{result.report.confidence}",
                    flush=True,
                )
        print(json.dumps(score_cases(cases, results), indent=2))
        return 0
    except (
        ConfigurationError,
        DriverError,
        Neo4jError,
        OpenAIError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
