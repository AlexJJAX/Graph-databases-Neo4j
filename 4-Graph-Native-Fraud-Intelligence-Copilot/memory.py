"""Neo4j-backed compact memory for multi-turn fraud investigations."""

from __future__ import annotations

from uuid import uuid4

from agent import InvestigationResult
from graph_store import FraudGraphStore


class GraphInvestigationMemory:
    def __init__(self, graph: FraudGraphStore, *, max_turns: int = 6):
        self._graph = graph
        self._max_turns = max(1, min(int(max_turns), 12))

    def new_id(self) -> str:
        return str(uuid4())

    def history(self, session_id: str) -> tuple[dict[str, str], ...]:
        return self._graph.history(session_id, self._max_turns)

    def remember(self, session_id: str, question: str, result: InvestigationResult) -> None:
        self._graph.remember(
            session_id, str(uuid4()), question.strip(),
            result.report.executive_summary.claim,
            result.report.risk_assessment.claim,
            result.report.confidence,
        )

    def clear(self, session_id: str) -> bool:
        return self._graph.clear_history(session_id)
