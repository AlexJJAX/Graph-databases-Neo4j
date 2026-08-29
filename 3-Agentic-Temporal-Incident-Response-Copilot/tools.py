"""Read-only, bounded tools exposed to the investigation model."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from evidence import EvidenceRecord, ToolResult, graph_fragment
from graph_store import OperationsGraphStore
from retrieval import OperationalRetriever


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_incidents",
        "description": "List known incidents so an investigation can resolve a case ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["all", "investigating", "resolved"],
                    "description": "Filter by incident status, or all.",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_incident_context",
        "description": "Get exact incident facts, impacted services, and alerts for a known case ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "ID such as INC-104."}
            },
            "required": ["incident_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_recent_changes",
        "description": "Find deployments to impacted or adjacent services before an incident began.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "lookback_minutes": {"type": "integer", "minimum": 15, "maximum": 1440},
            },
            "required": ["incident_id", "lookback_minutes"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "trace_blast_radius",
        "description": "Trace services that depend on a degraded service. Exposure is not proof of impact.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "max_hops": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["service_id", "max_hops"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_operational_evidence",
        "description": "Hybrid semantic and full-text search over runbook and postmortem chunks, graph-filtered by service.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "service_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "source_types": {"type": "array", "items": {"type": "string", "enum": ["runbook", "postmortem"]}, "maxItems": 2},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query", "service_ids", "source_types", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "find_similar_incidents",
        "description": "Find historical postmortem evidence matching an incident's symptoms and affected topology.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 6},
            },
            "required": ["incident_id", "query", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_runbooks",
        "description": "Retrieve deterministic runbook sections connected to one or more services.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}
            },
            "required": ["service_ids"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class InvestigationTools:
    """Dispatch tool calls without exposing arbitrary Cypher or write operations."""

    def __init__(self, graph: OperationsGraphStore, retriever: OperationalRetriever):
        self.graph = graph
        self.retriever = retriever
        self._dispatch: dict[str, Callable[..., ToolResult]] = {
            "list_incidents": self.list_incidents,
            "get_incident_context": self.get_incident_context,
            "get_recent_changes": self.get_recent_changes,
            "trace_blast_radius": self.trace_blast_radius,
            "search_operational_evidence": self.search_operational_evidence,
            "find_similar_incidents": self.find_similar_incidents,
            "get_runbooks": self.get_runbooks,
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._dispatch.get(name)
        if handler is None:
            raise ValueError(f"Unknown investigation tool: {name}")
        return handler(**arguments)

    def list_incidents(self, status: str) -> ToolResult:
        if status not in {"all", "investigating", "resolved"}:
            raise ValueError("status must be all, investigating, or resolved")
        rows = self.graph.incidents(None if status == "all" else status)
        evidence = tuple(
            EvidenceRecord(
                evidence_id="",
                kind="graph",
                source_id=row["incidentId"],
                title=f"{row['incidentId']} · {row['title']}",
                content=(
                    f"{row['severity']} {row['status']} incident started {row['startedAt']}. "
                    f"{row['summary']} Impacted services: {', '.join(row['serviceIds'])}."
                ),
                source_type="incident",
                occurred_at=row["startedAt"],
                metadata=row,
            )
            for row in rows
        )
        return ToolResult(summary=f"Found {len(rows)} incidents.", evidence=evidence)

    def get_incident_context(self, incident_id: str) -> ToolResult:
        row = self.graph.incident_context(incident_id.strip().upper())
        if row is None:
            return ToolResult(summary=f"No incident named {incident_id} exists.")
        incident_evidence = EvidenceRecord(
            evidence_id="",
            kind="graph",
            source_id=row["incidentId"],
            title=f"{row['incidentId']} · {row['title']}",
            content=(
                f"{row['severity']} incident is {row['status']}; started {row['startedAt']}. "
                f"{row['summary']} Observed impacted services: "
                + ", ".join(item["serviceId"] for item in row["impactedServices"])
                + "."
            ),
            source_type="incident",
            occurred_at=row["startedAt"],
            metadata={key: value for key, value in row.items() if key != "alerts"},
        )
        alerts = tuple(
            EvidenceRecord(
                evidence_id="",
                kind="telemetry",
                source_id=alert["alertId"],
                title=alert["name"],
                content=(
                    f"{alert['serviceId']} reported {alert['metric']} = "
                    f"{alert['value']} {alert['unit']} at {alert['firedAt']}."
                ),
                source_type="alert",
                occurred_at=alert["firedAt"],
                metadata=alert,
            )
            for alert in row["alerts"]
        )
        nodes = [
            {
                "id": row["incidentId"],
                "label": row["incidentId"],
                "type": "incident",
                "status": row["status"],
            }
        ]
        edges: list[dict[str, Any]] = []
        for service in row["impactedServices"]:
            nodes.append(
                {
                    "id": service["serviceId"],
                    "label": service["name"],
                    "type": "service",
                    "tier": service["tier"],
                }
            )
            edges.append(
                {
                    "source": row["incidentId"],
                    "target": service["serviceId"],
                    "relationship": "IMPACTED",
                }
            )
        return ToolResult(
            summary=f"Loaded {row['incidentId']} with {len(alerts)} alerts.",
            evidence=(incident_evidence, *alerts),
            graph=graph_fragment(nodes, edges),
            timeline=tuple(self.graph.timeline(row["incidentId"])),
        )

    def get_recent_changes(
        self, incident_id: str, lookback_minutes: int
    ) -> ToolResult:
        rows = self.graph.recent_changes(incident_id.strip().upper(), lookback_minutes)
        evidence = tuple(
            EvidenceRecord(
                evidence_id="",
                kind="timeline",
                source_id=row["deploymentId"],
                title=f"{row['deploymentId']} · {row['serviceName']}",
                content=(
                    f"Version {row['version']} was deployed to {row['serviceId']} at "
                    f"{row['deployedAt']}, {row['minutesBefore']} minutes before the incident. "
                    f"Commit {row['sha']}: {row['commitSummary']}."
                ),
                source_type="deployment",
                occurred_at=row["deployedAt"],
                metadata=row,
            )
            for row in rows
        )
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for row in rows:
            nodes.extend(
                [
                    {"id": row["deploymentId"], "label": row["version"], "type": "deployment"},
                    {"id": row["serviceId"], "label": row["serviceName"], "type": "service"},
                    {"id": row["sha"], "label": row["sha"], "type": "commit"},
                ]
            )
            edges.extend(
                [
                    {"source": row["deploymentId"], "target": row["serviceId"], "relationship": "DEPLOYED_TO"},
                    {"source": row["deploymentId"], "target": row["sha"], "relationship": "BUILT_FROM"},
                ]
            )
        return ToolResult(
            summary=f"Found {len(rows)} relevant changes before {incident_id.upper()}.",
            evidence=evidence,
            graph=graph_fragment(nodes, edges),
        )

    def trace_blast_radius(self, service_id: str, max_hops: int) -> ToolResult:
        rows = self.graph.blast_radius(service_id, max_hops)
        evidence = tuple(
            EvidenceRecord(
                evidence_id="",
                kind="graph",
                source_id=f"blast:{service_id}:{row['serviceId']}",
                title=f"Dependency path to {row['name']}",
                content=(
                    f"{row['serviceId']} is exposed through {row['hops']} dependency hop(s): "
                    + " → ".join(row["path"])
                    + ". This path indicates possible exposure, not observed impact."
                ),
                source_type="topology",
                metadata=row,
            )
            for row in rows
        )
        nodes: dict[str, dict[str, Any]] = {
            service_id: {"id": service_id, "label": service_id, "type": "service"}
        }
        edges: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            for current, following in zip(row["path"], row["path"][1:]):
                nodes.setdefault(current, {"id": current, "label": current, "type": "service"})
                nodes.setdefault(following, {"id": following, "label": following, "type": "service"})
                edges.setdefault(
                    (following, current),
                    {"source": following, "target": current, "relationship": "DEPENDS_ON"},
                )
        return ToolResult(
            summary=f"Found {len(rows)} dependent services within {max_hops} hops.",
            evidence=evidence,
            graph=graph_fragment(nodes.values(), edges.values()),
        )

    def search_operational_evidence(
        self,
        query: str,
        service_ids: list[str],
        source_types: list[str],
        top_k: int,
    ) -> ToolResult:
        result = self.retriever.search(
            query,
            service_ids=service_ids,
            source_types=source_types,
            top_k=top_k,
        )
        return ToolResult(
            summary=(
                f"Retrieved {len(result.evidence)} document chunks in "
                f"{result.elapsed_ms} ms."
            ),
            evidence=result.evidence,
        )

    def find_similar_incidents(
        self, incident_id: str, query: str, top_k: int
    ) -> ToolResult:
        context = self.graph.incident_context(incident_id.strip().upper())
        if context is None:
            return ToolResult(summary=f"No incident named {incident_id} exists.")
        service_ids = [item["serviceId"] for item in context["impactedServices"]]
        result = self.retriever.search(
            query,
            service_ids=service_ids,
            source_types=["postmortem"],
            top_k=top_k,
        )
        evidence = tuple(
            record
            for record in result.evidence
            if record.metadata.get("incident_id") != incident_id.upper()
        )
        return ToolResult(
            summary=f"Found {len(evidence)} historical postmortem excerpts.",
            evidence=evidence,
        )

    def get_runbooks(self, service_ids: list[str]) -> ToolResult:
        if not service_ids:
            raise ValueError("service_ids cannot be empty")
        rows = self.graph.runbook_sections(service_ids)
        evidence = tuple(
            EvidenceRecord(
                evidence_id="",
                kind="document",
                source_id=row["chunkId"],
                title=f"{row['title']} · {row['section']}",
                content=row["text"],
                source_type="runbook",
                metadata={
                    "runbook_id": row["runbookId"],
                    "service_ids": row["serviceIds"],
                    "sequence": row["sequence"],
                },
            )
            for row in rows
        )
        return ToolResult(
            summary=f"Loaded {len(rows)} connected runbook sections.",
            evidence=evidence,
        )


def tool_payload(summary: str, evidence: tuple[EvidenceRecord, ...]) -> str:
    """Serialize the bounded tool result returned to the model."""
    return json.dumps(
        {
            "summary": summary,
            "evidence": [record.as_dict() for record in evidence],
        },
        ensure_ascii=False,
    )


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
