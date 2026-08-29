from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent import (  # noqa: E402
    CitedClaim,
    IncidentInvestigationAgent,
    InvestigationDraft,
    InvestigationResult,
    ToolTrace,
    format_report,
    validate_report,
)
from evidence import EvidenceRecord, ToolResult  # noqa: E402
from evaluate import score_cases  # noqa: E402
from memory import SessionMemory  # noqa: E402


def evidence(evidence_id="E1"):
    return EvidenceRecord(
        evidence_id, "timeline", "D1", "Deployment", "Timeout changed.", "deployment"
    )


def cited(text="The timeout changed.", ids=None):
    return CitedClaim(claim=text, evidence_ids=ids if ids is not None else ["E1"])


def draft(ids=None):
    ids = ["E1"] if ids is None else ids
    claim = CitedClaim(claim="The timeout changed.", evidence_ids=ids)
    return InvestigationDraft(
        title="Incident report",
        summary=claim,
        leading_hypothesis=claim,
        confidence="moderate",
        supporting_evidence=[claim],
        contradicting_evidence=[],
        blast_radius=[],
        next_checks=[CitedClaim(claim="Compare configuration.", evidence_ids=ids)],
        limitations=[CitedClaim(claim="No traces are available.", evidence_ids=ids)],
    )


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def response(output, parsed=None):
    return SimpleNamespace(
        output=output,
        output_parsed=parsed,
        output_text="",
        usage=SimpleNamespace(input_tokens=50, output_tokens=12),
    )


class FakeTools:
    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult("Found deployment.", (evidence(""),))


class AgentMemoryEvaluationTests(unittest.TestCase):
    def test_agent_runs_tool_loop_and_validates_typed_report(self):
        call = SimpleNamespace(
            type="function_call", name="get_recent_changes",
            arguments=json.dumps({"incident_id": "INC-1", "lookback_minutes": 60}),
            call_id="call-1",
        )
        responses = FakeResponses([response([call]), response([], draft())])
        tools = FakeTools()
        agent = IncidentInvestigationAgent(
            tools, SimpleNamespace(responses=responses), "gpt-5.6-luna", max_rounds=4
        )
        result = agent.investigate("Investigate INC-1")

        self.assertEqual(result.evidence[0].evidence_id, "E1")
        self.assertEqual(result.trace[0].tool, "get_recent_changes")
        self.assertEqual(responses.calls[0]["model"], "gpt-5.6-luna")
        self.assertFalse(responses.calls[0]["store"])
        self.assertFalse(responses.calls[0]["parallel_tool_calls"])
        self.assertEqual(responses.calls[0]["reasoning"], {"effort": "low"})
        second_input = responses.calls[1]["input"]
        self.assertTrue(any(isinstance(item, dict) and item.get("type") == "function_call_output" for item in second_input))
        self.assertIn("[E1]", result.answer)
        self.assertNotIn("[E1] [E1]", result.answer)

    def test_unknown_and_missing_report_citations_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "unknown evidence"):
            validate_report(draft(["E9"]), [evidence()])
        uncited = CitedClaim.model_construct(
            claim="The timeout changed.", evidence_ids=[]
        )
        uncited_draft = draft()
        uncited_draft.summary = uncited
        with self.assertRaisesRegex(RuntimeError, "requires an evidence citation"):
            validate_report(uncited_draft, [evidence()])

    def test_format_report_renders_ids_separately_from_claim_text(self):
        report = draft()
        rendered = format_report(report)
        self.assertIn("The timeout changed. [E1]", rendered)
        self.assertIn("Next safe checks", rendered)

    def test_session_memory_is_bounded_and_clearable(self):
        memory = SessionMemory(max_turns=2)
        result = InvestigationResult(
            report=draft(), answer="answer", evidence=(evidence(),),
            graph={"nodes": [], "edges": []}, timeline=(), trace=(), metrics={},
        )
        for index in range(3):
            memory.remember("session", f"question {index}", result)
        history = memory.history("session")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["question"], "question 1")
        self.assertTrue(memory.clear("session"))
        self.assertEqual(memory.history("session"), ())

    def test_score_cases_measures_route_evidence_diagnosis_and_budget(self):
        result = SimpleNamespace(
            trace=(ToolTrace(1, "get_recent_changes", {}, "completed", "ok", ("E1",), 4),),
            evidence=(evidence(),),
            report=draft(),
            metrics={"tool_calls": 1},
        )
        cases = [{
            "expectedTools": ["get_recent_changes"],
            "expectedSourceIds": ["D1"],
            "expectedTerms": ["timeout"],
            "maxToolCalls": 2,
        }]
        scores = score_cases(cases, [result])
        self.assertEqual(scores["tool_route_recall"], 1.0)
        self.assertEqual(scores["evidence_source_hit_rate"], 1.0)
        self.assertEqual(scores["diagnosis_term_accuracy"], 1.0)
        self.assertEqual(scores["bounded_investigation_rate"], 1.0)

    def test_short_question_is_rejected_before_model_call(self):
        responses = FakeResponses([])
        agent = IncidentInvestigationAgent(
            FakeTools(), SimpleNamespace(responses=responses), "model"
        )
        with self.assertRaisesRegex(ValueError, "at least 3"):
            agent.investigate("x")
        self.assertEqual(responses.calls, [])


if __name__ == "__main__":
    unittest.main()
