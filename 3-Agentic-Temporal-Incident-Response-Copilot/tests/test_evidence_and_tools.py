from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from evidence import EvidenceLedger, EvidenceRecord, ToolResult  # noqa: E402
from retrieval import RetrievalResult  # noqa: E402
from tools import InvestigationTools, TOOL_DEFINITIONS, tool_payload  # noqa: E402


def record(source_id="s1", content="fact"):
    return EvidenceRecord("", "graph", source_id, "Title", content, "incident")


class FakeGraph:
    def incidents(self, status=None):
        return [{
            "incidentId": "INC-1", "title": "Case", "severity": "SEV-1",
            "status": status or "resolved", "startedAt": "2026-01-01T00:00:00Z",
            "summary": "A case.", "serviceIds": ["api"],
        }]

    def incident_context(self, incident_id):
        if incident_id == "MISSING":
            return None
        return {
            "incidentId": incident_id, "title": "Timeouts", "severity": "SEV-1",
            "status": "investigating", "summary": "Timeouts rose.",
            "startedAt": "2026-01-01T00:00:00Z", "endedAt": None,
            "impactedServices": [{"serviceId": "api", "name": "API", "tier": 1}],
            "alerts": [{"alertId": "A1", "name": "Timeout high", "metric": "timeouts",
                        "value": 12, "unit": "percent", "firedAt": "2026-01-01T00:01:00Z",
                        "serviceId": "api"}],
        }

    def timeline(self, incident_id):
        return [{"eventId": incident_id, "type": "incident", "occurredAt": "2026-01-01T00:00:00Z"}]

    def recent_changes(self, incident_id, lookback_minutes):
        return [{"deploymentId": "D1", "version": "v1", "status": "succeeded",
                 "deployedAt": "2025-12-31T23:55:00Z", "serviceId": "api",
                 "serviceName": "API", "sha": "abc", "commitSummary": "Reduce timeout",
                 "minutesBefore": 5}]

    def blast_radius(self, service_id, max_hops):
        return [{"serviceId": "edge", "name": "Edge", "tier": 1, "hops": 1,
                 "path": [service_id, "edge"]}]

    def runbook_sections(self, service_ids):
        return [{"runbookId": "R1", "title": "Triage", "chunkId": "R1:0",
                 "section": "Check", "sequence": 0, "text": "Inspect timeout.",
                 "serviceIds": service_ids}]


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return RetrievalResult(
            evidence=(EvidenceRecord("", "document", "P1:0", "Postmortem", "Retry storm.", "postmortem", metadata={"incident_id": "INC-OLD"}),),
            elapsed_ms=4,
        )


class EvidenceAndToolsTests(unittest.TestCase):
    def test_ledger_assigns_ids_deduplicates_and_merges_visuals(self):
        ledger = EvidenceLedger()
        result = ToolResult(
            "ok", (record(), record()),
            {"nodes": [{"id": "n1"}], "edges": [{"source": "n1", "target": "n2", "relationship": "R"}]},
            ({"eventId": "t1", "occurredAt": "2026-01-01"},),
        )
        assigned = ledger.add(result)
        self.assertEqual([item.evidence_id for item in assigned], ["E1", "E1"])
        self.assertEqual(len(ledger.records), 1)
        self.assertEqual(len(ledger.graph()["edges"]), 1)
        self.assertEqual(ledger.timeline()[0]["eventId"], "t1")

    def test_tool_definitions_are_strict_read_only_surface(self):
        names = {tool["name"] for tool in TOOL_DEFINITIONS}
        self.assertEqual(len(names), 7)
        self.assertNotIn("execute_cypher", names)
        self.assertFalse(any("write" in name or "rollback" in name for name in names))
        self.assertTrue(all(tool["strict"] for tool in TOOL_DEFINITIONS))

    def test_incident_context_separates_incident_and_alert_evidence(self):
        tools = InvestigationTools(FakeGraph(), FakeRetriever())
        result = tools.get_incident_context("inc-1")
        self.assertEqual([item.source_type for item in result.evidence], ["incident", "alert"])
        self.assertEqual(result.graph["edges"][0]["relationship"], "IMPACTED")
        self.assertEqual(result.timeline[0]["eventId"], "INC-1")

    def test_blast_radius_explicitly_marks_exposure_not_impact(self):
        tools = InvestigationTools(FakeGraph(), FakeRetriever())
        result = tools.trace_blast_radius("api", 2)
        self.assertIn("possible exposure, not observed impact", result.evidence[0].content)
        self.assertEqual(result.graph["edges"][0]["relationship"], "DEPENDS_ON")

    def test_similar_incidents_use_postmortem_and_service_filter(self):
        retriever = FakeRetriever()
        tools = InvestigationTools(FakeGraph(), retriever)
        result = tools.find_similar_incidents("INC-1", "timeouts", 3)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(retriever.calls[0][1]["source_types"], ["postmortem"])
        self.assertEqual(retriever.calls[0][1]["service_ids"], ["api"])

    def test_tool_payload_contains_only_assigned_evidence(self):
        payload = tool_payload("one fact", (record(),))
        self.assertIn('"summary": "one fact"', payload)
        self.assertIn('"evidence"', payload)

    def test_unknown_tool_is_rejected(self):
        tools = InvestigationTools(FakeGraph(), FakeRetriever())
        with self.assertRaisesRegex(ValueError, "Unknown investigation tool"):
            tools.execute("delete_everything", {})


if __name__ == "__main__":
    unittest.main()
