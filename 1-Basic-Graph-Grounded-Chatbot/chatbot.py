"""OpenAI tool-calling loop that grounds answers in Neo4j evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from graph import MovieEvidence, MovieGraph, SearchCriteria


SEARCH_TOOL = {
    "type": "function",
    "name": "search_movie_graph",
    "description": (
        "Search the Neo4j movie knowledge graph by movie title, person, genre, "
        "rating, and release year. Use empty arrays and null for filters that the "
        "user did not request."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "movie_titles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Movie titles or distinctive title fragments.",
            },
            "people": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Actor or director names mentioned by the user.",
            },
            "genres": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Movie genres explicitly requested by the user.",
            },
            "minimum_rating": {
                "anyOf": [
                    {"type": "number", "minimum": 0, "maximum": 10},
                    {"type": "null"},
                ],
                "description": "Minimum rating, or null when not requested.",
            },
            "released_from": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "description": "Inclusive earliest release year, or null.",
            },
            "released_to": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "description": "Inclusive latest release year, or null.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8,
                "description": "Maximum number of movies to retrieve.",
            },
        },
        "required": [
            "movie_titles",
            "people",
            "genres",
            "minimum_rating",
            "released_from",
            "released_to",
            "limit",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}


RETRIEVAL_INSTRUCTIONS = """
You route movie questions to a Neo4j knowledge graph.
Call search_movie_graph exactly once. Extract only filters stated by the user.
Names may be partial when that is all the user supplied. Use empty arrays and
null for absent filters. For broad recommendations, use a limit of 5.
""".strip()


ANSWER_INSTRUCTIONS = """
Answer the user's question using only facts in the search_movie_graph output.
Every factual claim about a movie, person, genre, year, rating, or plot must cite
the supporting evidence ID in square brackets, for example [G1]. If the tool
returned no matches, say that the graph does not contain enough evidence and ask
for a different title, person, genre, year, or rating. Never fill gaps from your
training knowledge. Be concise and useful. Do not call another tool.
""".strip()


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    evidence: tuple[tuple[str, MovieEvidence], ...]


class GroundedMovieChatbot:
    def __init__(self, graph: MovieGraph, openai_client: Any, model: str):
        self._graph = graph
        self._client = openai_client
        self._model = model

    def answer(self, question: str) -> GroundedAnswer:
        question = question.strip()
        if not question:
            raise ValueError("Question cannot be empty")

        input_items: list[Any] = [{"role": "user", "content": question}]
        retrieval_response = self._client.responses.create(
            model=self._model,
            reasoning={"effort": "low"},
            instructions=RETRIEVAL_INSTRUCTIONS,
            tools=[SEARCH_TOOL],
            tool_choice="required",
            parallel_tool_calls=False,
            input=input_items,
            store=False,
            max_output_tokens=600,
        )
        input_items += list(retrieval_response.output)

        evidence_by_movie: dict[str, tuple[str, MovieEvidence]] = {}
        handled_call = False
        for item in retrieval_response.output:
            if item.type != "function_call":
                continue
            if item.name != SEARCH_TOOL["name"]:
                raise RuntimeError(f"Unexpected tool requested: {item.name}")

            handled_call = True
            arguments = json.loads(item.arguments)
            criteria = SearchCriteria.from_tool_arguments(arguments)
            matches = self._graph.search_movies(criteria)

            call_facts: list[dict[str, Any]] = []
            for movie in matches:
                if movie.movie_id not in evidence_by_movie:
                    evidence_id = f"G{len(evidence_by_movie) + 1}"
                    evidence_by_movie[movie.movie_id] = (evidence_id, movie)
                evidence_id, evidence = evidence_by_movie[movie.movie_id]
                call_facts.append(evidence.as_grounding_fact(evidence_id))

            tool_output = {
                "status": "ok" if call_facts else "no_matches",
                "match_count": len(call_facts),
                "evidence": call_facts,
            }
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(tool_output),
                }
            )

        if not handled_call:
            raise RuntimeError("The model did not request graph evidence")

        answer_response = self._client.responses.create(
            model=self._model,
            reasoning={"effort": "low"},
            instructions=ANSWER_INSTRUCTIONS,
            tools=[SEARCH_TOOL],
            tool_choice="none",
            parallel_tool_calls=False,
            input=input_items,
            store=False,
            max_output_tokens=800,
        )
        answer_text = answer_response.output_text.strip()
        if not answer_text:
            raise RuntimeError("The model returned an empty answer")

        return GroundedAnswer(
            text=answer_text,
            evidence=tuple(evidence_by_movie.values()),
        )
