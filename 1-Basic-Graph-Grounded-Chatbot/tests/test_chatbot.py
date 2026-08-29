from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from chatbot import GroundedMovieChatbot  # noqa: E402
from graph import MovieEvidence  # noqa: E402


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            arguments = {
                "movie_titles": [],
                "people": ["Christopher Nolan"],
                "genres": [],
                "minimum_rating": 8.5,
                "released_from": None,
                "released_to": None,
                "limit": 5,
            }
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="search_movie_graph",
                        arguments=json.dumps(arguments),
                        call_id="call-1",
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(output=[], output_text="Inception is a match [G1].")


class FakeGraph:
    def __init__(self):
        self.criteria = None

    def search_movies(self, criteria):
        self.criteria = criteria
        return [
            MovieEvidence(
                movie_id="m1",
                title="Inception",
                released_year=2010,
                rating=8.8,
                overview="Dream infiltration.",
                directors=("Christopher Nolan",),
                cast=("Leonardo DiCaprio",),
                genres=("Sci-Fi",),
            )
        ]


class GroundedMovieChatbotTests(unittest.TestCase):
    def test_tool_call_is_executed_and_evidence_is_returned(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        graph = FakeGraph()
        chatbot = GroundedMovieChatbot(graph, client, "gpt-5.6-luna")

        answer = chatbot.answer("Which Nolan movies are rated above 8.5?")

        self.assertEqual(answer.text, "Inception is a match [G1].")
        self.assertEqual(answer.evidence[0][0], "G1")
        self.assertEqual(graph.criteria.people, ("Christopher Nolan",))
        self.assertEqual(responses.calls[0]["model"], "gpt-5.6-luna")
        self.assertEqual(responses.calls[0]["tool_choice"], "required")
        self.assertEqual(responses.calls[1]["tool_choice"], "none")
        tool_output = responses.calls[1]["input"][-1]
        self.assertEqual(tool_output["type"], "function_call_output")
        self.assertIn('"evidence_id": "G1"', tool_output["output"])

    def test_empty_question_is_rejected_before_any_api_call(self):
        responses = FakeResponses()
        chatbot = GroundedMovieChatbot(
            FakeGraph(), SimpleNamespace(responses=responses), "gpt-5.6-luna"
        )

        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            chatbot.answer("  ")
        self.assertEqual(responses.calls, [])


if __name__ == "__main__":
    unittest.main()
