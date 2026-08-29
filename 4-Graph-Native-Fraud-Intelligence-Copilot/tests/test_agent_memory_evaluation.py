from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent import (  # noqa: E402
    CitedClaim, FraudInvestigationAgent, FraudInvestigationDraft,
    InvestigationResult, ToolTrace, format_report, validate_report,
)
from evidence import EvidenceRecord, ToolResult  # noqa: E402
from evaluate import score_cases  # noqa: E402
from memory import GraphInvestigationMemory  # noqa: E402


def evidence(evidence_id="E1"):
    return EvidenceRecord(evidence_id, "alert", "ALRT-1", "Alert", "Observed alert fact.", "alert")


def draft(ids=None):
    ids = ["E1"] if ids is None else ids
    claim = CitedClaim(claim="The observed pattern warrants human review.", evidence_ids=ids)
    return FraudInvestigationDraft(
        title="Fraud investigation", executive_summary=claim, risk_assessment=claim,
        risk_level="high", confidence="moderate", observed_facts=[claim],
        derived_patterns=[], typology_matches=[], benign_or_contradictory_evidence=[],
        network_exposure=[], recommended_checks=[claim], limitations=[claim],
    )


class FakeResponses:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    def parse(self, **kwargs): self.calls.append(kwargs); return self.responses.pop(0)


def response(output, parsed=None):
    return SimpleNamespace(output=output, output_parsed=parsed, output_text="", usage=SimpleNamespace(input_tokens=40, output_tokens=10))


class FakeTools:
    def execute(self, name, arguments): return ToolResult("Found alert.", (evidence(""),))


class FakeGraphMemory:
    def __init__(self): self.turns = []; self.cleared = []
    def history(self, session_id, limit): return tuple(self.turns[-limit:])
    def remember(self, session_id, turn_id, question, summary, risk_assessment, confidence): self.turns.append({"question": question, "summary": summary, "risk_assessment": risk_assessment, "confidence": confidence})
    def clear_history(self, session_id): self.cleared.append(session_id); self.turns.clear(); return True


class AgentMemoryEvaluationTests(unittest.TestCase):
    def test_agent_runs_strict_tool_loop_and_citation_review(self):
        call = SimpleNamespace(type="function_call", name="get_alert_context", arguments=json.dumps({"alert_id": "ALRT-1"}), call_id="call-1")
        responses = FakeResponses([response([call]), response([], draft())])
        agent = FraudInvestigationAgent(FakeTools(), SimpleNamespace(responses=responses), "gpt-5.6-luna")
        result = agent.investigate("Investigate ALRT-1")
        self.assertEqual(result.evidence[0].evidence_id, "E1")
        self.assertEqual(result.metrics["grounding_review"], "passed")
        self.assertFalse(responses.calls[0]["parallel_tool_calls"])
        self.assertFalse(responses.calls[0]["store"])
        self.assertIs(responses.calls[0]["text_format"], FraudInvestigationDraft)
        self.assertTrue(any(isinstance(item, dict) and item.get("type") == "function_call_output" for item in responses.calls[1]["input"]))

    def test_unknown_missing_and_empty_evidence_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "unknown evidence"): validate_report(draft(["E9"]), [evidence()])
        uncited = CitedClaim.model_construct(claim="A claim", evidence_ids=[])
        report = draft(); report.executive_summary = uncited
        with self.assertRaisesRegex(RuntimeError, "requires an evidence citation"): validate_report(report, [evidence()])
        with self.assertRaisesRegex(RuntimeError, "without retrieved evidence"): validate_report(draft(), [])

    def test_report_format_separates_epistemic_sections(self):
        rendered = format_report(draft())
        self.assertIn("Risk assessment · high risk", rendered)
        self.assertIn("Observed facts", rendered)
        self.assertIn("Recommended human checks", rendered)
        self.assertIn("[E1]", rendered)

    def test_graph_memory_persists_compact_turns_and_clears(self):
        graph = FakeGraphMemory(); memory = GraphInvestigationMemory(graph, max_turns=2)
        result = InvestigationResult(draft(), "answer", (evidence(),), {"nodes": [], "edges": []}, (), (), {})
        memory.remember("session", "question", result)
        self.assertEqual(memory.history("session")[0]["question"], "question")
        self.assertTrue(memory.clear("session")); self.assertEqual(memory.history("session"), ())

    def test_evaluation_scores_routes_grounding_language_and_budget(self):
        result = SimpleNamespace(
            trace=(ToolTrace(1, "get_alert_context", {}, "completed", "ok", ("E1",), 1),),
            evidence=(evidence(),), report=draft(), answer=format_report(draft()), metrics={"tool_calls": 1},
        )
        scores = score_cases([{"expectedTools": ["get_alert_context"], "expectedSourceIds": ["ALRT-1"], "expectedTerms": ["review"], "maxToolCalls": 2}], [result])
        self.assertTrue(all(value == 1.0 for value in scores.values()))

    def test_short_question_is_rejected_without_model_call(self):
        responses = FakeResponses([])
        agent = FraudInvestigationAgent(FakeTools(), SimpleNamespace(responses=responses), "model")
        with self.assertRaisesRegex(ValueError, "at least 3"): agent.investigate("x")
        self.assertFalse(responses.calls)


if __name__ == "__main__": unittest.main()
