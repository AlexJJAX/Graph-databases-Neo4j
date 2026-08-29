"""Route, evidence, grounding, and risk-language evaluation for Project 4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError, PROJECT_DIR
from graph_store import FraudGraphStore
from runtime import build_agent


DEFAULT_EVAL_SET = PROJECT_DIR / "evals" / "questions.json"


def score_cases(cases: list[dict[str, Any]], results: list[Any]) -> dict[str, float]:
    route_scores: list[float] = []
    source_hits = term_hits = bounded = citation_valid = calibrated = 0
    forbidden = ("is fraudulent", "committed fraud", "is a fraudster", "guilty of fraud")
    for case, result in zip(cases, results, strict=True):
        used = {item.tool for item in result.trace}
        expected_tools = set(case.get("expectedTools", []))
        route_scores.append(len(used & expected_tools) / len(expected_tools) if expected_tools else 1.0)
        source_ids = {record.source_id for record in result.evidence}
        expected_sources = set(case.get("expectedSourceIds", []))
        source_hits += int(not expected_sources or bool(source_ids & expected_sources))
        answer = result.answer.lower()
        terms = [item.lower() for item in case.get("expectedTerms", [])]
        term_hits += int(not terms or all(item in answer for item in terms))
        bounded += int(result.metrics["tool_calls"] <= case.get("maxToolCalls", 8))
        valid_ids = {record.evidence_id for record in result.evidence}
        cited_ids = {item for claim in __import__("agent").report_claims(result.report) for item in claim.evidence_ids}
        citation_valid += int(bool(cited_ids) and cited_ids <= valid_ids)
        calibrated += int(not any(item in answer for item in forbidden))
    count = len(cases)
    return {
        "cases": float(count),
        "tool_route_recall": sum(route_scores) / count if count else 0.0,
        "evidence_source_hit_rate": source_hits / count if count else 0.0,
        "expected_term_accuracy": term_hits / count if count else 0.0,
        "citation_integrity_rate": citation_valid / count if count else 0.0,
        "calibrated_language_rate": calibrated / count if count else 0.0,
        "bounded_investigation_rate": bounded / count if count else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the fraud investigation agent.")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET)
    args = parser.parse_args()
    try:
        cases = json.loads(args.eval_set.read_text(encoding="utf-8"))
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        with FraudGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            agent = build_agent(config, graph, client)
            results = []
            for case in cases:
                print(f"{case['id']}: running...", flush=True)
                result = agent.investigate(case["question"])
                results.append(result)
                print(f"{case['id']}: {[item.tool for item in result.trace]} · {result.report.risk_level}/{result.report.confidence}", flush=True)
        print(json.dumps(score_cases(cases, results), indent=2))
        return 0
    except (ConfigurationError, DriverError, Neo4jError, OpenAIError, OSError, RuntimeError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
