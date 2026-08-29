from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from evidence import EvidenceLedger, EvidenceRecord, ToolResult  # noqa: E402
from retrieval import RetrievalResult  # noqa: E402
from tools import FraudInvestigationTools, TOOL_DEFINITIONS, tool_payload  # noqa: E402


class FakeGraph:
    def alerts(self, status=None):
        return [{"alertId": "ALRT-1", "title": "Cycle", "severity": "high", "status": status or "open", "createdAt": "2026-01-01T00:00:00Z", "reason": "Rule fired.", "accountIds": ["A-1", "A-2", "A-3"], "caseId": "CASE-1"}]
    def alert_context(self, alert_id):
        if alert_id == "MISSING": return None
        return {"alertId": alert_id, "title": "Cycle", "severity": "high", "status": "open", "reason": "Rule fired.", "createdAt": "2026-01-01T00:10:00Z", "caseId": "CASE-1", "accounts": [{"accountId": "A-1", "product": "current", "accountStatus": "active", "openedAt": "2025-01-01", "balance": 10, "personId": "P-1", "personName": "Person", "riskTier": "standard"}], "transactions": [{"transactionId": "T-1", "amount": 100, "currency": "GBP", "occurredAt": "2026-01-01T00:01:00Z", "channel": "payment", "senderAccountId": "A-1", "receiverAccountId": "A-2", "merchantId": None, "merchantName": None, "deviceId": "D-1"}]}
    def alert_network(self, alert_id): return {"nodes": [{"id": alert_id}], "edges": []}
    def transaction_timeline(self, alert_id): return [{"eventId": "T-1", "occurredAt": "2026-01-01T00:01:00Z"}]
    def shared_identifiers(self, account_ids): return [{"identifierId": "D-1", "identifierType": "device", "display": "fp", "accountIds": account_ids, "persons": [{"personId": "P-1", "name": "One"}, {"personId": "P-2", "name": "Two"}]}]
    def fund_flows(self, account_ids, window_hours): return [{"transactionId": "T-1", "senderAccountId": "A-1", "receiverAccountId": "A-2", "merchantId": None, "merchantName": None, "deviceId": "D-1", "amount": 100, "currency": "GBP", "occurredAt": "2026-01-01T00:01:00Z", "channel": "payment"}]
    def transaction_cycles(self, account_ids, max_minutes): return [{"accountPath": ["A-1", "A-2", "A-3", "A-1"], "transactionIds": ["T-1", "T-2", "T-3"], "amounts": [100, 98, 96], "startedAt": "2026-01-01T00:01:00Z", "endedAt": "2026-01-01T00:09:00Z", "elapsedMinutes": 8}]
    def merchant_concentration(self, account_ids, window_hours): return [{"merchantId": "M-1", "merchantName": "Voucher", "category": "digital", "riskLevel": "elevated", "merchantAmount": 80, "totalOutgoing": 100, "percentage": 80.0, "transactionIds": ["T-9"]}]


class FakeRetriever:
    def __init__(self): self.calls = []
    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return RetrievalResult((EvidenceRecord("", "document", "fraud:CASE:00", "Case", "Similar pattern.", "case_report", score=.8),), 4)


class EvidenceToolsTests(unittest.TestCase):
    def setUp(self): self.tools = FraudInvestigationTools(FakeGraph(), FakeRetriever())

    def test_ledger_assigns_ids_deduplicates_and_merges(self):
        record = EvidenceRecord("", "graph", "S", "Title", "Fact", "account")
        ledger = EvidenceLedger(); assigned = ledger.add(ToolResult("ok", (record, record), {"nodes": [{"id": "n"}], "edges": []}, ({"eventId": "t", "occurredAt": "2026"},)))
        self.assertEqual([item.evidence_id for item in assigned], ["E1", "E1"])
        self.assertEqual((len(ledger.records), len(ledger.graph()["nodes"])), (1, 1))

    def test_tool_surface_is_strict_and_has_no_arbitrary_query_or_action(self):
        names = {item["name"] for item in TOOL_DEFINITIONS}
        self.assertEqual(len(names), 8)
        self.assertNotIn("execute_cypher", names)
        self.assertFalse(any("block" in name or "file_report" in name for name in names))
        self.assertTrue(all(item["strict"] for item in TOOL_DEFINITIONS))

    def test_alert_context_separates_alert_entities_and_transactions(self):
        result = self.tools.get_alert_context("alrt-1")
        self.assertEqual([item.kind for item in result.evidence], ["alert", "entity", "transaction"])
        self.assertIn("not a fraud determination", result.evidence[0].content)
        self.assertEqual(result.timeline[0]["eventId"], "T-1")

    def test_shared_identifier_is_explicitly_only_a_signal(self):
        result = self.tools.find_shared_identifiers(["A-1", "A-2"])
        self.assertIn("not proof of common control", result.evidence[0].content)
        self.assertEqual(result.evidence[0].source_id, "D-1")

    def test_flow_cycle_and_concentration_are_distinct_evidence(self):
        flow = self.tools.trace_fund_flows(["A-1"], 24)
        cycle = self.tools.detect_transaction_cycles(["A-1", "A-2", "A-3"], 60)
        concentration = self.tools.measure_merchant_concentration(["A-1"], 24)
        self.assertEqual(flow.evidence[0].kind, "transaction")
        self.assertEqual(cycle.evidence[0].kind, "derived_pattern")
        self.assertIn("not a fraud determination", cycle.evidence[0].content)
        self.assertIn("80.0%", concentration.evidence[0].content)

    def test_similar_cases_are_semantic_leads(self):
        result = self.tools.find_similar_cases("rapid pass-through", 3)
        self.assertIn("not proof", result.summary)
        self.assertEqual(self.tools.retriever.calls[0][1]["source_types"], ["case_report"])

    def test_tool_payload_and_unknown_tool(self):
        payload = tool_payload("summary", (EvidenceRecord("E1", "x", "s", "t", "c", "x"),))
        self.assertIn('"evidence_id": "E1"', payload)
        with self.assertRaisesRegex(ValueError, "Unknown fraud"): self.tools.execute("delete_accounts", {})


if __name__ == "__main__": unittest.main()
