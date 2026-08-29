from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import ValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent import CitedClaim, FraudInvestigationDraft, InvestigationResult  # noqa: E402
from config import AppConfig, Neo4jConfig  # noqa: E402
from evidence import EvidenceRecord  # noqa: E402
from web import InvestigateRequest, WebRuntime, create_app  # noqa: E402


class FakeGraph:
    def verify_connectivity(self): pass
    def close(self): pass
    def is_ready(self): return True
    def stats(self): return {"personCount": 3, "accountCount": 3, "transactionCount": 3, "alertCount": 1, "caseCount": 1, "chunkCount": 4}
    def alerts(self, status=None): return [{"alertId": "ALRT-1", "title": "Cycle", "severity": "high", "status": "open", "createdAt": "2026-01-01T00:00:00Z", "reason": "Cycle detected.", "accountIds": ["A-1"], "caseId": "CASE-1"}]
    def cases(self): return [{"caseId": "CASE-1", "title": "Case", "status": "investigating", "priority": "P1", "openedAt": "2026", "assignee": "Unassigned", "alertIds": ["ALRT-1"]}]
    def alert_context(self, alert_id): return {"alertId": alert_id, "title": "Cycle", "severity": "high", "status": "open", "reason": "Cycle detected.", "createdAt": "2026", "caseId": "CASE-1", "accounts": [], "transactions": []} if alert_id == "ALRT-1" else None
    def alert_network(self, alert_id): return {"nodes": [{"id": alert_id, "label": alert_id, "type": "alert"}], "edges": []}
    def transaction_timeline(self, alert_id): return []


class FakeMemory:
    def __init__(self): self.turns = []
    def new_id(self): return "session-12345678"
    def history(self, session_id): return tuple(self.turns)
    def remember(self, session_id, question, result): self.turns.append({"question": question, "summary": result.report.executive_summary.claim, "risk_assessment": result.report.risk_assessment.claim, "confidence": result.report.confidence})
    def clear(self, session_id): self.turns.clear(); return True


def result():
    claim = CitedClaim(claim="Observed pattern warrants review.", evidence_ids=["E1"])
    report = FraudInvestigationDraft(title="Assessment", executive_summary=claim, risk_assessment=claim, risk_level="moderate", confidence="low", observed_facts=[claim], derived_patterns=[], typology_matches=[], benign_or_contradictory_evidence=[], network_exposure=[], recommended_checks=[claim], limitations=[claim])
    evidence = EvidenceRecord("E1", "alert", "ALRT-1", "Alert", "Rule fired.", "alert")
    return InvestigationResult(report, "answer", (evidence,), {"nodes": [], "edges": []}, (), (), {"tool_calls": 0, "evidence_count": 1, "total_ms": 2})


class FakeAgent:
    def __init__(self): self.calls = []
    def investigate(self, question, *, history): self.calls.append((question, history)); return result()


class WebUiTests(unittest.TestCase):
    def runtime(self):
        runtime = WebRuntime(AppConfig(Neo4jConfig("bolt://x", "u", "p"), "key"), FakeGraph(), SimpleNamespace(), FakeMemory())
        runtime._agent = FakeAgent(); return runtime

    def test_request_validation(self):
        self.assertEqual(InvestigateRequest(question="Investigate alert").alert_id, None)
        with self.assertRaises(ValidationError): InvestigateRequest(question="no")
        with self.assertRaises(ValidationError): InvestigateRequest(question="valid question", session_id="short")

    def test_status_meta_network_and_investigation_endpoints(self):
        runtime = self.runtime()
        with TestClient(create_app(lambda: runtime)) as client:
            status = client.get("/api/status").json(); self.assertTrue(status["persistent_graph_memory"]); self.assertTrue(status["read_only_tools"])
            self.assertEqual(client.get("/api/meta").json()["alerts"][0]["alertId"], "ALRT-1")
            self.assertEqual(client.get("/api/network/ALRT-1").json()["graph"]["nodes"][0]["id"], "ALRT-1")
            response = client.post("/api/investigate", json={"question": "Trace this alert", "alert_id": "ALRT-1"})
            self.assertEqual(response.status_code, 200); self.assertEqual(response.json()["report"]["title"], "Assessment")
        self.assertIn("Selected alert: ALRT-1", runtime._agent.calls[0][0])

    def test_second_turn_receives_persisted_history_and_clear(self):
        runtime = self.runtime()
        with TestClient(create_app(lambda: runtime)) as client:
            first = client.post("/api/investigate", json={"question": "First question"}).json()
            client.post("/api/investigate", json={"question": "Second question", "session_id": first["session_id"]})
            cleared = client.delete(f"/api/sessions/{first['session_id']}").json()
        self.assertEqual(len(runtime._agent.calls[1][1]), 1); self.assertTrue(cleared["cleared"])

    def test_ui_exposes_alert_graph_timeline_dossier_and_evidence(self):
        html = (PROJECT_DIR / "static" / "index.html").read_text()
        for marker in ('id="alertList"', 'id="networkSvg"', 'id="timelineStrip"', 'id="reportPanel"', 'id="evidencePanel"', 'id="tracePanel"'):
            self.assertIn(marker, html)
        self.assertIn("Evidence only", html); self.assertIn("No auto-action", html); self.assertNotIn("cdn.", html.lower())

    def test_ui_script_has_graph_interaction_citations_memory_and_resizers(self):
        script = (PROJECT_DIR / "static" / "app.js").read_text()
        self.assertIn('addEventListener("wheel"', script)
        self.assertIn("data-evidence-id", script)
        self.assertIn("/api/sessions/", script)
        self.assertIn("localStorage", script)
        self.assertIn('"--left-width"', script); self.assertIn('"--right-width"', script)
        self.assertIn("layoutNodes", script); self.assertIn("renderTimeline", script)

    def test_styles_are_responsive_accessible_and_motion_safe(self):
        styles = (PROJECT_DIR / "static" / "styles.css").read_text()
        self.assertIn(":focus-visible", styles)
        self.assertIn("prefers-reduced-motion", styles)
        self.assertIn("@media (max-width: 620px)", styles)


if __name__ == "__main__": unittest.main()
