"""Small process-local investigation memory for multi-turn web sessions."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from uuid import uuid4

from agent import InvestigationResult


class SessionMemory:
    def __init__(self, *, max_turns: int = 6):
        self._max_turns = max(1, int(max_turns))
        self._turns: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._lock = Lock()

    def new_id(self) -> str:
        return str(uuid4())

    def history(self, session_id: str) -> tuple[dict[str, str], ...]:
        with self._lock:
            return tuple(dict(turn) for turn in self._turns.get(session_id, ()))

    def remember(
        self, session_id: str, question: str, result: InvestigationResult
    ) -> None:
        turn = {
            "question": question.strip(),
            "summary": result.report.summary.claim,
            "leading_hypothesis": result.report.leading_hypothesis.claim,
            "confidence": result.report.confidence,
        }
        with self._lock:
            self._turns[session_id].append(turn)
            self._turns[session_id] = self._turns[session_id][-self._max_turns :]

    def clear(self, session_id: str) -> bool:
        with self._lock:
            return self._turns.pop(session_id, None) is not None
