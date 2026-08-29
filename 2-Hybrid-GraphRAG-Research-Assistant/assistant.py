"""Citation-grounded answer generation and evidence graph projection."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from retrieval import Evidence, ResearchRetriever, SearchFilters


CITATION_PATTERN = re.compile(r"\[(R\d+)\]")


ANSWER_INSTRUCTIONS = """
You are an AI research analyst. Answer using only the supplied Neo4j GraphRAG
evidence. Cite every factual claim with one or more evidence IDs such as [R1].
Explain relationships between papers only when the graph context supports them.
Never use unstated training knowledge, invent a result, or cite an unknown ID.
Prefer a short synthesis over a list of disconnected excerpts. If the evidence
is incomplete, state the precise limitation.
""".strip()


@dataclass(frozen=True, slots=True)
class AssistantResult:
    answer: str
    evidence: tuple[Evidence, ...]
    graph: dict[str, list[dict[str, Any]]]
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "evidence": [item.as_dict() for item in self.evidence],
            "graph": self.graph,
            "metrics": self.metrics,
        }


def validate_citations(answer: str, evidence: tuple[Evidence, ...]) -> None:
    valid = {item.evidence_id for item in evidence}
    used = set(CITATION_PATTERN.findall(answer))
    unknown = used - valid
    if unknown:
        raise RuntimeError("Answer cited unknown evidence: " + ", ".join(sorted(unknown)))
    if valid and not used:
        raise RuntimeError("Answer did not cite its graph evidence")


def build_evidence_graph(evidence: tuple[Evidence, ...]) -> dict[str, list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_node(node_id: str, label: str, node_type: str, **metadata: Any) -> None:
        nodes.setdefault(
            node_id,
            {"id": node_id, "label": label, "type": node_type, **metadata},
        )

    def add_edge(source: str, target: str, relationship: str) -> None:
        key = (source, target, relationship)
        edges.setdefault(
            key,
            {"source": source, "target": target, "relationship": relationship},
        )

    for item in evidence:
        paper_id = f"paper:{item.paper_id}"
        chunk_id = f"chunk:{item.chunk_id}"
        add_node(paper_id, item.title, "paper", year=item.year)
        add_node(chunk_id, item.evidence_id, "chunk", section=item.section)
        add_edge(paper_id, chunk_id, "HAS_CHUNK")

        for author in item.authors[:4]:
            author_id = f"author:{author}"
            add_node(author_id, author, "author")
            add_edge(author_id, paper_id, "AUTHORED")
        for topic in item.topics[:4]:
            topic_id = f"topic:{topic}"
            add_node(topic_id, topic, "topic")
            add_edge(paper_id, topic_id, "ABOUT")
        for method in item.methods[:3]:
            method_id = f"method:{method}"
            add_node(method_id, method, "method")
            add_edge(paper_id, method_id, "USES_METHOD")
        for cited in item.cited_papers[:3]:
            if not cited.get("paperId"):
                continue
            cited_id = f"paper:{cited['paperId']}"
            add_node(cited_id, cited.get("title") or cited["paperId"], "paper")
            add_edge(paper_id, cited_id, "CITES")

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


class ResearchAssistant:
    def __init__(self, retriever: ResearchRetriever, openai_client: Any, model: str):
        self._retriever = retriever
        self._client = openai_client
        self._model = model

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> AssistantResult:
        retrieval = self._retriever.search(question, top_k=top_k, filters=filters)
        evidence = retrieval.evidence
        graph = build_evidence_graph(evidence)
        if not evidence:
            return AssistantResult(
                answer=(
                    "The research graph does not contain sufficiently relevant "
                    "evidence for that question. Try an AI-research concept, paper, "
                    "method, author, or dataset represented in the corpus."
                ),
                evidence=(),
                graph=graph,
                metrics={
                    "retrieval_ms": retrieval.elapsed_ms,
                    "generation_ms": 0,
                    "evidence_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            )

        prompt = {
            "question": question.strip(),
            "evidence": [item.as_context() for item in evidence],
        }
        started = time.perf_counter()
        response = self._client.responses.create(
            model=self._model,
            reasoning={"effort": "low"},
            instructions=ANSWER_INSTRUCTIONS,
            input=json.dumps(prompt, ensure_ascii=False),
            store=False,
            max_output_tokens=900,
        )
        generation_ms = int((time.perf_counter() - started) * 1000)
        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("The model returned an empty answer")
        validate_citations(answer, evidence)

        usage = getattr(response, "usage", None)
        return AssistantResult(
            answer=answer,
            evidence=evidence,
            graph=graph,
            metrics={
                "retrieval_ms": retrieval.elapsed_ms,
                "generation_ms": generation_ms,
                "evidence_count": len(evidence),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            },
        )
