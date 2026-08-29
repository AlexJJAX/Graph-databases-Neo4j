# Movie-question workflow

## CLI modes

`1-Basic-Graph-Grounded-Chatbot/app.py` supports:

- `--check`: load configuration and verify Neo4j without an OpenAI request.
- `--question` / `-q`: answer one question and exit.
- `--show-context`: print the exact evidence records supplied to the model.
- no question: run an interactive prompt; `quit` and `exit` terminate it.

## Grounded answer path

The chatbot rejects an empty question, then makes a first Responses API call with `tool_choice="required"` and `parallel_tool_calls=False`. The model must call `search_movie_graph` exactly once and extract only filters stated by the user. The graph executes the bounded search and the chatbot assigns stable per-response IDs (`G1`, `G2`, ...).

A second Responses API call receives the original request, the tool call, and JSON evidence. It uses `tool_choice="none"`, may not call another tool, and is instructed to use only returned facts. Factual claims about movies, people, genres, years, ratings, and plots must cite an evidence ID. If retrieval is empty, the intended answer says the graph lacks enough evidence instead of filling gaps from model knowledge.

## Change watch-outs

Changes to the tool schema, `SearchCriteria`, Cypher projection, or answer instructions can weaken grounding while leaving the CLI apparently functional. Update the focused unit tests when changing those boundaries; use `--show-context` when manually checking what reaches the model.

Source anchors: `1-Basic-Graph-Grounded-Chatbot/chatbot.py`, `app.py`, and the project README.