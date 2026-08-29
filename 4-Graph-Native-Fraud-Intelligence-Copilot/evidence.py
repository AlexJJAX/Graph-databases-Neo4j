"""Typed evidence ledger shared by every fraud investigation tool."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    source_id: str
    title: str
    content: str
    source_type: str
    occurred_at: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> str:
        digest = hashlib.sha1(self.content.encode("utf-8")).hexdigest()[:12]
        return f"{self.kind}:{self.source_id}:{digest}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "source_type": self.source_type,
            "occurred_at": self.occurred_at,
            "score": round(self.score, 4) if self.score is not None else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    summary: str
    evidence: tuple[EvidenceRecord, ...] = ()
    graph: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"nodes": [], "edges": []}
    )
    timeline: tuple[dict[str, Any], ...] = ()


class EvidenceLedger:
    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []
        self._by_key: dict[str, EvidenceRecord] = {}
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._timeline: dict[str, dict[str, Any]] = {}

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def add(self, result: ToolResult) -> tuple[EvidenceRecord, ...]:
        assigned: list[EvidenceRecord] = []
        for record in result.evidence:
            stored = self._by_key.get(record.dedup_key())
            if stored is None:
                stored = replace(record, evidence_id=f"E{len(self._records) + 1}")
                self._records.append(stored)
                self._by_key[record.dedup_key()] = stored
            assigned.append(stored)
        for node in result.graph.get("nodes", []):
            if node.get("id"):
                current = self._nodes.setdefault(str(node["id"]), {})
                current.update(node)
        for edge in result.graph.get("edges", []):
            key = (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("relationship", "")),
            )
            if all(key):
                self._edges.setdefault(key, dict(edge))
        for event in result.timeline:
            if event.get("eventId"):
                self._timeline.setdefault(str(event["eventId"]), dict(event))
        return tuple(assigned)

    def graph(self) -> dict[str, list[dict[str, Any]]]:
        return {"nodes": list(self._nodes.values()), "edges": list(self._edges.values())}

    def timeline(self) -> list[dict[str, Any]]:
        return sorted(self._timeline.values(), key=lambda event: event.get("occurredAt") or "")

    def context(self, *, limit: int = 40) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self._records[:limit]]


def graph_fragment(
    nodes: Iterable[dict[str, Any]], edges: Iterable[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    return {"nodes": list(nodes), "edges": list(edges)}
