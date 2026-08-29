"""Seed a small movie graph only when the database has no Movie nodes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError

from config import ConfigurationError, Neo4jConfig
from graph import MovieGraph


DATA_FILE = Path(__file__).resolve().parent / "data" / "movies.json"


def main() -> int:
    try:
        config = Neo4jConfig.from_env()
        movies = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        with MovieGraph(config) as graph:
            graph.verify_connectivity()
            existing_count = graph.count_movies()
            if existing_count:
                print(
                    f"Seed skipped: database already contains {existing_count} Movie nodes. "
                    "The chatbot will use the existing graph."
                )
                return 0

            graph.create_schema()
            processed = graph.seed_movies(movies)
            print(f"Seeded {processed} movies into database '{config.database}'.")
        return 0
    except (ConfigurationError, DriverError, Neo4jError, OSError, ValueError) as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
