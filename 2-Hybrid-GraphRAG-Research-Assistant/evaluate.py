"""Retrieval evaluation for the curated Project 2 question set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from config import AppConfig, ConfigurationError, PROJECT_DIR
from embeddings import OpenAI2Embedder
from graph_store import ResearchGraphStore
from retrieval import ResearchRetriever, SearchFilters


DEFAULT_EVAL_SET = PROJECT_DIR / "evals" / "questions.json"


def score_cases(cases: list[dict], retrieved: list[list[str]]) -> dict[str, float]:
    positive = 0
    hits = 0
    reciprocal_rank_total = 0.0
    negative = 0
    negative_rejections = 0

    for case, paper_ids in zip(cases, retrieved, strict=True):
        expected = set(case["expectedPaperIds"])
        if not expected:
            negative += 1
            negative_rejections += int(not paper_ids)
            continue
        positive += 1
        first_rank = next(
            (index for index, paper_id in enumerate(paper_ids, start=1) if paper_id in expected),
            None,
        )
        if first_rank is not None:
            hits += 1
            reciprocal_rank_total += 1 / first_rank

    return {
        "positive_cases": float(positive),
        "hit_rate_at_k": hits / positive if positive else 0.0,
        "mean_reciprocal_rank": reciprocal_rank_total / positive if positive else 0.0,
        "negative_cases": float(negative),
        "negative_rejection_rate": (
            negative_rejections / negative if negative else 0.0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate hybrid retrieval.")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    try:
        cases = json.loads(args.eval_set.read_text(encoding="utf-8"))
        config = AppConfig.from_env()
        client = OpenAI(api_key=config.openai_api_key)
        embedder = OpenAI2Embedder(
            client, config.embedding_model, config.embedding_dimensions
        )
        with ResearchGraphStore(config.neo4j) as graph:
            graph.verify_connectivity()
            if not graph.is_ready():
                raise RuntimeError("Run ingest.py before evaluation")
            retriever = ResearchRetriever(
                driver=graph.driver,
                database=graph.database,
                embedder=embedder,
                minimum_semantic_score=config.minimum_semantic_score,
            )
            retrieved: list[list[str]] = []
            for case in cases:
                result = retriever.search(
                    case["question"],
                    top_k=args.top_k,
                    filters=SearchFilters(**case.get("filters", {})),
                )
                paper_ids = [item.paper_id for item in result.evidence]
                retrieved.append(paper_ids)
                print(f"{case['id']}: {paper_ids}")

        print(json.dumps(score_cases(cases, retrieved), indent=2))
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
