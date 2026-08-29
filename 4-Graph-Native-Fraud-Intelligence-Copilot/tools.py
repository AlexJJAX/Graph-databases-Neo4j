"""Strict, read-only tools exposed to the fraud investigation model."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from evidence import EvidenceRecord, ToolResult, graph_fragment
from graph_store import FraudGraphStore
from retrieval import FraudEvidenceRetriever


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {"type": "function", "name": "list_alerts", "description": "List known fraud alerts to resolve an alert ID.", "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["all", "open", "closed"]}}, "required": ["status"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "get_alert_context", "description": "Get observed alert, account-owner, and flagged-transaction facts.", "parameters": {"type": "object", "properties": {"alert_id": {"type": "string"}}, "required": ["alert_id"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "find_shared_identifiers", "description": "Find devices, phones, or addresses shared by selected accounts. A shared identifier is a signal, not proof of common control.", "parameters": {"type": "object", "properties": {"account_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 12}}, "required": ["account_ids"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "trace_fund_flows", "description": "Trace observed transfers and merchant payments involving selected accounts in a bounded time window.", "parameters": {"type": "object", "properties": {"account_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 12}, "window_hours": {"type": "integer", "minimum": 1, "maximum": 720}}, "required": ["account_ids", "window_hours"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "detect_transaction_cycles", "description": "Detect exact three-account directed transfer cycles completed inside a bounded interval.", "parameters": {"type": "object", "properties": {"account_ids": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 12}, "max_minutes": {"type": "integer", "minimum": 5, "maximum": 1440}}, "required": ["account_ids", "max_minutes"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "measure_merchant_concentration", "description": "Measure the observed share of selected accounts' outgoing value sent to each merchant.", "parameters": {"type": "object", "properties": {"account_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 12}, "window_hours": {"type": "integer", "minimum": 1, "maximum": 720}}, "required": ["account_ids", "window_hours"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "search_fraud_evidence", "description": "Hybrid vector and full-text search over typologies, policy, and linked case-report chunks.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "account_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 12}, "source_types": {"type": "array", "items": {"type": "string", "enum": ["typology", "policy", "case_report"]}, "maxItems": 3}, "top_k": {"type": "integer", "minimum": 1, "maximum": 8}}, "required": ["query", "account_ids", "source_types", "top_k"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "find_similar_cases", "description": "Search historical case reports for semantically similar observed patterns and outcomes.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 6}}, "required": ["query", "top_k"], "additionalProperties": False}, "strict": True},
]


def _node(node_id: str | None, label: str | None, node_type: str, **extra: Any) -> dict[str, Any] | None:
    return {"id": node_id, "label": label or node_id, "type": node_type, **extra} if node_id else None


class FraudInvestigationTools:
    def __init__(self, graph: FraudGraphStore, retriever: FraudEvidenceRetriever):
        self.graph = graph
        self.retriever = retriever
        self._dispatch: dict[str, Callable[..., ToolResult]] = {
            "list_alerts": self.list_alerts,
            "get_alert_context": self.get_alert_context,
            "find_shared_identifiers": self.find_shared_identifiers,
            "trace_fund_flows": self.trace_fund_flows,
            "detect_transaction_cycles": self.detect_transaction_cycles,
            "measure_merchant_concentration": self.measure_merchant_concentration,
            "search_fraud_evidence": self.search_fraud_evidence,
            "find_similar_cases": self.find_similar_cases,
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._dispatch.get(name)
        if handler is None:
            raise ValueError(f"Unknown fraud investigation tool: {name}")
        return handler(**arguments)

    def list_alerts(self, status: str) -> ToolResult:
        if status not in {"all", "open", "closed"}:
            raise ValueError("status must be all, open, or closed")
        rows = self.graph.alerts(None if status == "all" else status)
        evidence = tuple(EvidenceRecord(
            "", "alert", row["alertId"], f"{row['alertId']} · {row['title']}",
            f"{row['severity']} alert is {row['status']}; created {row['createdAt']}. {row['reason']} Flagged accounts: {', '.join(row['accountIds'])}.",
            "alert", row["createdAt"], metadata=row,
        ) for row in rows)
        return ToolResult(f"Found {len(rows)} alerts.", evidence)

    def get_alert_context(self, alert_id: str) -> ToolResult:
        alert_id = alert_id.strip().upper()
        row = self.graph.alert_context(alert_id)
        if row is None:
            return ToolResult(f"No alert named {alert_id} exists.")
        alert = EvidenceRecord(
            "", "alert", row["alertId"], f"{row['alertId']} · {row['title']}",
            f"{row['severity']} alert is {row['status']}. Rule reason: {row['reason']} This is an alert, not a fraud determination.",
            "alert", row["createdAt"], metadata={key: value for key, value in row.items() if key not in {"accounts", "transactions"}},
        )
        accounts = tuple(EvidenceRecord(
            "", "entity", account["accountId"], f"{account['accountId']} · {account['personName']}",
            f"{account['personName']} ({account['personId']}) controls {account['accountId']}, a {account['product']} account opened {account['openedAt']} with status {account['accountStatus']}.",
            "account", metadata=account,
        ) for account in row["accounts"])
        transactions = tuple(EvidenceRecord(
            "", "transaction", tx["transactionId"], f"{tx['transactionId']} · {tx['currency']} {tx['amount']:,.2f}",
            f"At {tx['occurredAt']}, {tx['senderAccountId']} sent {tx['currency']} {tx['amount']:,.2f} to {tx.get('receiverAccountId') or tx.get('merchantName')} via {tx['channel']} using {tx.get('deviceId') or 'an unrecorded device'}.",
            "transaction", tx["occurredAt"], metadata=tx,
        ) for tx in row["transactions"])
        graph = self.graph.alert_network(alert_id)
        return ToolResult(f"Loaded {alert_id} with {len(accounts)} accounts and {len(transactions)} flagged transactions.", (alert, *accounts, *transactions), graph, tuple(self.graph.transaction_timeline(alert_id)))

    def find_shared_identifiers(self, account_ids: list[str]) -> ToolResult:
        ids = list(dict.fromkeys(item.strip().upper() for item in account_ids if item.strip()))[:12]
        if len(ids) < 2:
            raise ValueError("At least two account IDs are required")
        rows = self.graph.shared_identifiers(ids)
        evidence = tuple(EvidenceRecord(
            "", "relationship", row["identifierId"], f"Shared {row['identifierType']} · {row['identifierId']}",
            f"Observed {row['identifierType']} {row['identifierId']} is linked to accounts {', '.join(row['accountIds'])}. This overlap is a relationship signal, not proof of common control.",
            row["identifierType"], metadata=row,
        ) for row in rows)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for row in rows:
            nodes.append(_node(row["identifierId"], row["identifierId"], row["identifierType"], display=row.get("display")))
            for person in row["persons"]:
                nodes.append(_node(person["personId"], person["name"], "person"))
                edges.append({"source": person["personId"], "target": row["identifierId"], "relationship": "SHARES"})
        return ToolResult(f"Found {len(rows)} identifiers shared across the selected accounts.", evidence, graph_fragment((item for item in nodes if item), edges))

    def trace_fund_flows(self, account_ids: list[str], window_hours: int) -> ToolResult:
        ids = list(dict.fromkeys(item.strip().upper() for item in account_ids if item.strip()))[:12]
        rows = self.graph.fund_flows(ids, window_hours)
        evidence = tuple(EvidenceRecord(
            "", "transaction", row["transactionId"], f"{row['transactionId']} · observed flow",
            f"{row['senderAccountId']} sent {row['currency']} {row['amount']:,.2f} to {row.get('receiverAccountId') or row.get('merchantName')} at {row['occurredAt']} via {row['channel']}.",
            "transaction", row["occurredAt"], metadata=row,
        ) for row in rows)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        for row in rows:
            target = row.get("receiverAccountId") or row.get("merchantId")
            nodes.extend([_node(row["senderAccountId"], row["senderAccountId"], "account"), _node(target, row.get("merchantName") or target, "merchant" if row.get("merchantId") else "account")])
            edges.append({"source": row["senderAccountId"], "target": target, "relationship": "PAID" if row.get("merchantId") else "TRANSFERRED", "amount": row["amount"], "transactionId": row["transactionId"]})
            timeline.append({"eventId": row["transactionId"], "type": "transaction", "occurredAt": row["occurredAt"], "label": f"{row['senderAccountId']} → {target}", "detail": f"{row['currency']} {row['amount']:,.2f}"})
        return ToolResult(f"Traced {len(rows)} observed flows in the {window_hours}-hour window.", evidence, graph_fragment((item for item in nodes if item), edges), tuple(timeline))

    def detect_transaction_cycles(self, account_ids: list[str], max_minutes: int) -> ToolResult:
        rows = self.graph.transaction_cycles(account_ids, max_minutes)
        evidence = tuple(EvidenceRecord(
            "", "derived_pattern", "cycle:" + ":".join(row["transactionIds"]), "Directed three-account cycle",
            f"Observed transfers {' → '.join(row['accountPath'])} formed a directed cycle in {row['elapsedMinutes']} minutes. Transaction IDs: {', '.join(row['transactionIds'])}; amounts: {row['amounts']}. This is a derived graph pattern, not a fraud determination.",
            "cycle", row["startedAt"], metadata=row,
        ) for row in rows)
        return ToolResult(f"Found {len(rows)} directed three-account cycles within {max_minutes} minutes.", evidence)

    def measure_merchant_concentration(self, account_ids: list[str], window_hours: int) -> ToolResult:
        rows = self.graph.merchant_concentration(account_ids, window_hours)
        evidence = tuple(EvidenceRecord(
            "", "derived_pattern", row["merchantId"], f"Merchant concentration · {row['merchantName']}",
            f"Observed payments to {row['merchantName']} totalled GBP {row['merchantAmount']:,.2f}, {row['percentage']:.1f}% of selected-account outgoing value in the bounded window. Merchant risk label: {row['riskLevel']}.",
            "merchant_concentration", metadata=row,
        ) for row in rows)
        nodes = [_node(row["merchantId"], row["merchantName"], "merchant", risk=row["riskLevel"]) for row in rows]
        return ToolResult(f"Measured concentration across {len(rows)} merchants.", evidence, graph_fragment((item for item in nodes if item), []))

    def search_fraud_evidence(self, query: str, account_ids: list[str], source_types: list[str], top_k: int) -> ToolResult:
        result = self.retriever.search(query, account_ids=account_ids, source_types=source_types, top_k=top_k)
        return ToolResult(f"Retrieved {len(result.evidence)} grounded document chunks in {result.elapsed_ms} ms.", result.evidence)

    def find_similar_cases(self, query: str, top_k: int) -> ToolResult:
        result = self.retriever.search(query, account_ids=[], source_types=["case_report"], top_k=top_k)
        return ToolResult(f"Found {len(result.evidence)} semantically similar historical case-report chunks. Similarity is a lead, not proof of the same outcome.", result.evidence)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def tool_payload(summary: str, evidence: tuple[EvidenceRecord, ...]) -> str:
    return json.dumps({"summary": summary, "evidence": [record.as_dict() for record in evidence]}, ensure_ascii=False)
