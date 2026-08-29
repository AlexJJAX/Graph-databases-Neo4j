"""Command-line entry point for the basic graph-grounded chatbot."""

from __future__ import annotations

import argparse
import sys

from neo4j.exceptions import DriverError, Neo4jError
from openai import OpenAI, OpenAIError

from chatbot import GroundedAnswer, GroundedMovieChatbot
from config import AppConfig, ConfigurationError
from graph import MovieGraph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask grounded questions about the Neo4j movie graph."
    )
    parser.add_argument("--question", "-q", help="Ask one question and exit.")
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Print the graph evidence supplied to the model.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify configuration and Neo4j connectivity without calling OpenAI.",
    )
    return parser


def print_answer(answer: GroundedAnswer, show_context: bool) -> None:
    print(f"\nAssistant\n{answer.text}")
    if not show_context:
        return

    print("\nRetrieved graph evidence")
    if not answer.evidence:
        print("(no matching graph facts)")
        return

    for evidence_id, movie in answer.evidence:
        year = movie.released_year if movie.released_year is not None else "unknown year"
        rating = movie.rating if movie.rating is not None else "unrated"
        print(f"[{evidence_id}] {movie.title} ({year}) — rating {rating}")
        print(f"     directors: {', '.join(movie.directors) or 'unknown'}")
        print(f"     cast: {', '.join(movie.cast) or 'unknown'}")
        print(f"     genres: {', '.join(movie.genres) or 'unknown'}")


def run_question(chatbot: GroundedMovieChatbot, question: str, show_context: bool) -> None:
    answer = chatbot.answer(question)
    print_answer(answer, show_context)


def interactive_loop(chatbot: GroundedMovieChatbot, show_context: bool) -> None:
    print("Graph-Grounded Movie Assistant")
    print("Ask about titles, actors, directors, genres, years, or ratings.")
    print("Type 'quit' to exit.\n")
    while True:
        try:
            question = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if question.lower() in {"quit", "exit"}:
            return
        if not question:
            continue
        run_question(chatbot, question, show_context)
        print()


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = AppConfig.from_env()
        with MovieGraph(config.neo4j) as graph:
            graph.verify_connectivity()
            if args.check:
                print(
                    f"Ready: Neo4j '{config.neo4j.database}' is reachable; "
                    f"model is {config.openai_model}."
                )
                return 0

            client = OpenAI(api_key=config.openai_api_key)
            chatbot = GroundedMovieChatbot(graph, client, config.openai_model)
            if args.question:
                run_question(chatbot, args.question, args.show_context)
            else:
                interactive_loop(chatbot, args.show_context)
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
