from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import ValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent import CitedClaim, InvestigationDraft, InvestigationResult  # noqa: E402
from config import AppConfig, Neo4jConfig  # noqa: E402
from memory import SessionMemory  # noqa: E402
from web import InvestigateRequest, WebRuntime, create_app  # noqa: E402


class FakeGraph:
    def verify_connectivity(self):
        pass

    def close(self):
        pass

    def is_ready(self):
        return True

    def stats(self):
        return {"serviceCount": 2, "incidentCount": 1, "deploymentCount": 1, "alertCount": 1, "chunkCount": 3}

    def incidents(self, status=None):
        return [{"incidentId": "INC-1", "title": "Case", "severity": "SEV-1", "status": "investigating", "startedAt": "2026-01-01T00:00:00Z", "summary": "Case summary", "serviceIds": ["api"]}]

    def services(self):
        return [{"serviceId": "api", "name": "API", "tier": 1, "layer": 0, "team": "Team"}]

    def topology(self, incident_id=None):
        return {"nodes": [{"id": "api", "label": "API", "tier": 1, "layer": 0}], "edges": []}

    def timeline(self, incident_id):
        return [{"eventId": incident_id, "type": "incident", "occurredAt": "2026-01-01T00:00:00Z", "label": "Case"}]


def result():
    claim = CitedClaim(claim="Grounded claim.", evidence_ids=["E1"])
    return InvestigationResult(
        report=InvestigationDraft(
            title="Report", summary=claim, leading_hypothesis=claim,
            confidence="low", supporting_evidence=[], contradicting_evidence=[],
            blast_radius=[], next_checks=[], limitations=[],
        ),
        answer="Grounded claim.", evidence=(), graph={"nodes": [], "edges": []},
        timeline=(), trace=(),
        metrics={"tool_calls": 0, "evidence_count": 0, "total_ms": 2},
    )


class FakeAgent:
    def __init__(self):
        self.calls = []

    def investigate(self, question, *, history):
        self.calls.append((question, history))
        return result()


class WebAndUiContractTests(unittest.TestCase):
    def runtime(self):
        config = AppConfig(
            Neo4jConfig("bolt://x", "u", "p"), "key",
        )
        runtime = WebRuntime(config, FakeGraph(), SimpleNamespace(), SessionMemory())
        runtime._agent = FakeAgent()
        return runtime

    def test_request_model_validates_bounds(self):
        self.assertEqual(InvestigateRequest(question="Investigate INC-1").session_id, None)
        with self.assertRaises(ValidationError):
            InvestigateRequest(question="no")
        with self.assertRaises(ValidationError):
            InvestigateRequest(question="valid question", session_id="short")

    def test_status_meta_topology_and_investigation_endpoints(self):
        runtime = self.runtime()
        with TestClient(create_app(lambda: runtime)) as client:
            self.assertTrue(client.get("/api/status").json()["read_only_tools"])
            self.assertEqual(client.get("/api/meta").json()["incidents"][0]["incidentId"], "INC-1")
            topology = client.get("/api/topology?incident_id=INC-1").json()
            self.assertEqual(topology["graph"]["nodes"][0]["id"], "api")
            response = client.post("/api/investigate", json={"question": "Investigate INC-1"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["session_id"])
            self.assertEqual(response.json()["report"]["title"], "Report")

    def test_second_turn_receives_session_history(self):
        runtime = self.runtime()
        with TestClient(create_app(lambda: runtime)) as client:
            first = client.post("/api/investigate", json={"question": "First question"}).json()
            client.post("/api/investigate", json={"question": "Second question", "session_id": first["session_id"]})
        self.assertEqual(len(runtime._agent.calls[1][1]), 1)

    def test_ui_has_topology_timeline_dossier_and_accessible_controls(self):
        html = (PROJECT_DIR / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="topologySvg"', html)
        self.assertIn('id="timelineTrack"', html)
        self.assertIn('id="evidencePanel"', html)
        self.assertIn('id="tracePanel"', html)
        self.assertIn("Read only", html)
        self.assertIn("aria-live", html)
        self.assertIn('id="caseFileResizer"', html)
        self.assertIn('id="dossierResizer"', html)
        self.assertIn('id="timelineResizer"', html)
        self.assertEqual(html.count('role="separator"'), 3)
        self.assertNotIn("cdn.", html.lower())

    def test_ui_script_exposes_pan_zoom_sessions_and_citations(self):
        script = (PROJECT_DIR / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("wheel"', script)
        self.assertIn('addEventListener("pointermove"', script)
        self.assertIn('setProperty("--case-file-width"', script)
        self.assertIn('setProperty("--dossier-width"', script)
        self.assertIn('setProperty("--timeline-panel-height"', script)
        self.assertIn('addEventListener("keydown"', script)
        self.assertIn("TOPOLOGY_BANDS", script)
        self.assertIn("topologyBandViewBoxSpan", script)
        self.assertIn("scheduleTopologyRender", script)
        self.assertIn('data-topology-band', script)
        self.assertNotIn("x: 75 + layer * 220", script)
        self.assertIn("/api/sessions/", script)
        self.assertIn("data-evidence-id", script)
        self.assertIn("parallel", (PROJECT_DIR / "README.md").read_text(encoding="utf-8") if (PROJECT_DIR / "README.md").exists() else "")

    def test_styles_include_responsive_focus_and_reduced_motion_rules(self):
        styles = (PROJECT_DIR / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", styles)
        self.assertIn("prefers-reduced-motion", styles)
        self.assertIn("@media (max-width: 720px)", styles)


if __name__ == "__main__":
    unittest.main()
