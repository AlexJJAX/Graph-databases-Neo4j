from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from graph import MovieEvidence, MovieGraph, SearchCriteria  # noqa: E402


class FakeDriver:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def execute_query(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.records, object(), ["title"]


class SearchCriteriaTests(unittest.TestCase):
    def test_tool_arguments_are_normalized_and_bounded(self):
        criteria = SearchCriteria.from_tool_arguments(
            {
                "movie_titles": [" Inception "],
                "people": ["Christopher Nolan"],
                "genres": [],
                "minimum_rating": 8,
                "released_from": 2000,
                "released_to": None,
                "limit": 99,
            }
        )

        self.assertEqual(criteria.movie_titles, ("Inception",))
        self.assertEqual(criteria.minimum_rating, 8.0)
        self.assertEqual(criteria.limit, 8)

    def test_invalid_year_range_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "released_from"):
            SearchCriteria.from_tool_arguments(
                {
                    "movie_titles": [],
                    "people": [],
                    "genres": [],
                    "minimum_rating": None,
                    "released_from": 2020,
                    "released_to": 2000,
                    "limit": 5,
                }
            )


class MovieEvidenceTests(unittest.TestCase):
    def test_record_is_projected_to_json_safe_evidence(self):
        evidence = MovieEvidence.from_record(
            {
                "movieId": "m1",
                "title": "Inception",
                "releasedYear": 2010,
                "rating": 8.8,
                "overview": "Dreams within dreams.",
                "directors": ["Christopher Nolan"],
                "cast": ["Leonardo DiCaprio"],
                "genres": ["Sci-Fi"],
            }
        )

        self.assertEqual(evidence.title, "Inception")
        self.assertEqual(evidence.directors, ("Christopher Nolan",))
        self.assertEqual(evidence.as_grounding_fact("G1")["evidence_id"], "G1")


class MovieGraphTests(unittest.TestCase):
    def test_search_uses_parameterized_cypher_and_named_database(self):
        fake_driver = FakeDriver(
            [
                {
                    "movieId": "m1",
                    "title": "Inception",
                    "releasedYear": 2010,
                    "rating": 8.8,
                    "overview": "Dreams within dreams.",
                    "directors": ["Christopher Nolan"],
                    "cast": ["Leonardo DiCaprio"],
                    "genres": ["Sci-Fi"],
                }
            ]
        )
        graph = object.__new__(MovieGraph)
        graph._driver = fake_driver
        graph._database = "neo4j"

        results = graph.search_movies(SearchCriteria(people=("Nolan",)))

        query, kwargs = fake_driver.calls[0]
        self.assertTrue(query.startswith("CYPHER 25"))
        self.assertIn("$people", query)
        self.assertNotIn("Nolan", query)
        self.assertEqual(kwargs["parameters_"]["people"], ["Nolan"])
        self.assertEqual(kwargs["database_"], "neo4j")
        self.assertEqual(results[0].movie_id, "m1")


if __name__ == "__main__":
    unittest.main()
