"""Neo4j access layer for the movie knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from neo4j import GraphDatabase, RoutingControl

from config import Neo4jConfig


SEARCH_MOVIES_QUERY = """
CYPHER 25
MATCH (movie:Movie)
WHERE (size($movieTitles) = 0 OR any(
        requestedTitle IN $movieTitles
        WHERE toLower(movie.title) CONTAINS toLower(requestedTitle)
      ))
  AND ($minimumRating IS NULL OR movie.imdbRating >= $minimumRating)
  AND ($releasedFrom IS NULL OR movie.releasedYear >= $releasedFrom)
  AND ($releasedTo IS NULL OR movie.releasedYear <= $releasedTo)
  AND (size($people) = 0 OR EXISTS {
        MATCH (person:Person)-[:ACTED_IN|DIRECTED]->(movie)
        WHERE any(
          requestedPerson IN $people
          WHERE toLower(person.name) CONTAINS toLower(requestedPerson)
        )
      })
  AND (size($genres) = 0 OR EXISTS {
        MATCH (movie)-[:IN_GENRE]->(matchedGenre:Genre)
        WHERE any(
          requestedGenre IN $genres
          WHERE toLower(matchedGenre.name) CONTAINS toLower(requestedGenre)
        )
      })
WITH movie
ORDER BY movie.imdbRating DESC, movie.votes DESC, movie.title
LIMIT $limit
RETURN movie.movieId AS movieId,
       movie.title AS title,
       movie.releasedYear AS releasedYear,
       movie.imdbRating AS rating,
       movie.overview AS overview,
       COLLECT {
         MATCH (director:Person)-[:DIRECTED]->(movie)
         RETURN director.name
         ORDER BY director.name
       } AS directors,
       COLLECT {
         MATCH (actor:Person)-[credit:ACTED_IN]->(movie)
         RETURN actor.name
         ORDER BY credit.billingOrder
         LIMIT 8
       } AS cast,
       COLLECT {
         MATCH (movie)-[:IN_GENRE]->(genre:Genre)
         RETURN genre.name
         ORDER BY genre.name
       } AS genres
""".strip()


SCHEMA_QUERIES = (
    "CYPHER 25 CREATE CONSTRAINT movie_movie_id_unique IF NOT EXISTS "
    "FOR (movie:Movie) REQUIRE movie.movieId IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT person_name_unique IF NOT EXISTS "
    "FOR (person:Person) REQUIRE person.name IS UNIQUE",
    "CYPHER 25 CREATE CONSTRAINT genre_name_unique IF NOT EXISTS "
    "FOR (genre:Genre) REQUIRE genre.name IS UNIQUE",
    "CYPHER 25 CREATE TEXT INDEX movie_title_text_idx IF NOT EXISTS "
    "FOR (movie:Movie) ON (movie.title)",
)


SEED_MOVIES_QUERY = """
CYPHER 25
UNWIND $movies AS row
MERGE (movie:Movie {movieId: row.movieId})
SET movie.title = row.title,
    movie.releasedYear = row.releasedYear,
    movie.imdbRating = row.imdbRating,
    movie.runtimeMinutes = row.runtimeMinutes,
    movie.overview = row.overview,
    movie.votes = row.votes,
    movie.source = 'portfolio-demo'
FOREACH (directorName IN row.directors |
  MERGE (director:Person {name: directorName})
  MERGE (director)-[:DIRECTED]->(movie)
)
FOREACH (credit IN row.cast |
  MERGE (actor:Person {name: credit.name})
  MERGE (actor)-[actedIn:ACTED_IN]->(movie)
  SET actedIn.billingOrder = credit.billingOrder
)
FOREACH (genreName IN row.genres |
  MERGE (genre:Genre {name: genreName})
  MERGE (movie)-[:IN_GENRE]->(genre)
)
RETURN count(movie) AS moviesProcessed
""".strip()


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    cleaned = tuple(str(item).strip() for item in value if str(item).strip())
    return cleaned[:5]


def _optional_number(value: Any, field_name: str, cast: type) -> Any:
    if value is None:
        return None
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number or null") from exc


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    movie_titles: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    minimum_rating: float | None = None
    released_from: int | None = None
    released_to: int | None = None
    limit: int = 5

    @classmethod
    def from_tool_arguments(cls, arguments: Mapping[str, Any]) -> "SearchCriteria":
        limit = _optional_number(arguments.get("limit", 5), "limit", int)
        minimum_rating = _optional_number(
            arguments.get("minimum_rating"), "minimum_rating", float
        )
        released_from = _optional_number(
            arguments.get("released_from"), "released_from", int
        )
        released_to = _optional_number(
            arguments.get("released_to"), "released_to", int
        )
        if limit is None:
            raise ValueError("limit must be an integer")
        if minimum_rating is not None and not 0 <= minimum_rating <= 10:
            raise ValueError("minimum_rating must be between 0 and 10")
        if (
            released_from is not None
            and released_to is not None
            and released_from > released_to
        ):
            raise ValueError("released_from cannot be later than released_to")

        return cls(
            movie_titles=_string_list(arguments.get("movie_titles", []), "movie_titles"),
            people=_string_list(arguments.get("people", []), "people"),
            genres=_string_list(arguments.get("genres", []), "genres"),
            minimum_rating=minimum_rating,
            released_from=released_from,
            released_to=released_to,
            limit=max(1, min(limit, 8)),
        )

    def as_parameters(self) -> dict[str, Any]:
        return {
            "movieTitles": list(self.movie_titles),
            "people": list(self.people),
            "genres": list(self.genres),
            "minimumRating": self.minimum_rating,
            "releasedFrom": self.released_from,
            "releasedTo": self.released_to,
            "limit": self.limit,
        }


@dataclass(frozen=True, slots=True)
class MovieEvidence:
    movie_id: str
    title: str
    released_year: int | None
    rating: float | None
    overview: str
    directors: tuple[str, ...]
    cast: tuple[str, ...]
    genres: tuple[str, ...]

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "MovieEvidence":
        return cls(
            movie_id=str(record.get("movieId") or record["title"]),
            title=str(record["title"]),
            released_year=record.get("releasedYear"),
            rating=record.get("rating"),
            overview=str(record.get("overview") or "")[:600],
            directors=tuple(record.get("directors") or ()),
            cast=tuple(record.get("cast") or ()),
            genres=tuple(record.get("genres") or ()),
        )

    def as_grounding_fact(self, evidence_id: str) -> dict[str, Any]:
        return {
            "evidence_id": evidence_id,
            "movie_id": self.movie_id,
            "title": self.title,
            "released_year": self.released_year,
            "rating": self.rating,
            "overview": self.overview,
            "directors": list(self.directors),
            "cast": list(self.cast),
            "genres": list(self.genres),
        }


class MovieGraph:
    """Owns one Neo4j driver and exposes bounded graph operations."""

    def __init__(self, config: Neo4jConfig):
        self._database = config.database
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )

    def __enter__(self) -> "MovieGraph":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    def search_movies(self, criteria: SearchCriteria) -> list[MovieEvidence]:
        records, _, _ = self._driver.execute_query(
            SEARCH_MOVIES_QUERY,
            parameters_=criteria.as_parameters(),
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        return [MovieEvidence.from_record(record) for record in records]

    def count_movies(self) -> int:
        records, _, _ = self._driver.execute_query(
            "CYPHER 25 MATCH (movie:Movie) RETURN count(movie) AS movieCount LIMIT 1",
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        return int(records[0]["movieCount"])

    def create_schema(self) -> None:
        for query in SCHEMA_QUERIES:
            self._driver.execute_query(query, database_=self._database)

    def seed_movies(self, movies: Sequence[Mapping[str, Any]]) -> int:
        records, _, _ = self._driver.execute_query(
            SEED_MOVIES_QUERY,
            movies=[dict(movie) for movie in movies],
            database_=self._database,
        )
        return int(records[0]["moviesProcessed"])
