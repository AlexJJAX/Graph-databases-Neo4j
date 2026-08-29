# Movie graph domain

## Graph model

The chatbot stores a movie catalog using these relationships:

```text
(:Person)-[:DIRECTED]->(:Movie)-[:IN_GENRE]->(:Genre)
(:Person)-[:ACTED_IN {billingOrder}]->(:Movie)
```

`Movie.movieId`, `Person.name`, and `Genre.name` have uniqueness constraints. A text index is created for movie titles. Seeded movie properties include title, release year, IMDb rating, runtime, votes, overview, and source metadata. The checked-in `data/movies.json` is a six-movie demo snapshot; ratings and votes are not live data.

## Seeding behavior

`seed.py` verifies connectivity, counts `Movie` nodes, and exits without changes if any already exist. For an empty database it creates the schema and uses `MERGE` to load the JSON records and their people, cast relationships, and genres. This protects an existing catalog but also means the seed does not reconcile or refresh a partially populated database.

## Retrieval contract

`SearchCriteria` accepts title fragments, people, genres, minimum rating, inclusive release-year bounds, and a result limit. Values are normalized and bounded: up to five values per list, ratings from 0–10, and one to eight movies. Results are ordered by rating, vote count, then title. Each movie returns directors, up to eight billing-ordered cast members, genres, and an overview truncated to 600 characters.

Queries use parameterized Cypher 25 and case-insensitive `CONTAINS` matching for titles, people, and genres. Because filters are literal and structured, paraphrased concepts are not semantic matches.

## Source anchors

- Schema, query, criteria validation, and evidence projection: `1-Basic-Graph-Grounded-Chatbot/graph.py`
- Initialization policy: `1-Basic-Graph-Grounded-Chatbot/seed.py`
- Demo records: `1-Basic-Graph-Grounded-Chatbot/data/movies.json`
