"""Bounded tool loop and citation-validated fraud investigation synthesis."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from evidence import EvidenceLedger, EvidenceRecord
from tools import FraudInvestigationTools, TOOL_DEFINITIONS, elapsed_ms, tool_payload


AGENT_INSTRUCTIONS = """
You are a read-only financial-crime investigator for the fictional Northstar
Financial dataset. Investigate by calling the supplied bounded tools. Prefer
exact graph and transaction facts for entities, identifiers, and fund flows;
use hybrid retrieval for policy, typologies, and historical case reports.

Every factual final-report claim must cite evidence IDs in its evidence_ids
field. Never put citation brackets in claim text and never invent an ID, fact,
relationship, score, or outcome. Keep four epistemic levels separate:
observed facts, application-derived graph patterns, retrieved typology matches,
and risk assessment. Shared identifiers, graph proximity, alerts, cycles, and
similar cases are signals—not proof of fraud or common control. Actively seek
benign or contradictory evidence and state missing evidence.

Use calibrated language such as "consistent with" or "warrants review". Do not
declare a person guilty or a transaction fraudulent. You may recommend
reversible evidence-gathering checks and human escalation, but cannot block an
account, file a report, contact a customer, run arbitrary Cypher, or perform an
external action. Return the typed report once evidence is sufficient or the
bounded investigation cannot progress.
""".strip()


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=3, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class FraudInvestigationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=160)
    executive_summary: CitedClaim
    risk_assessment: CitedClaim
    risk_level: Literal["low", "moderate", "high", "critical"]
    confidence: Literal["low", "moderate", "high"]
    observed_facts: list[CitedClaim] = Field(default_factory=list, max_length=10)
    derived_patterns: list[CitedClaim] = Field(default_factory=list, max_length=8)
    typology_matches: list[CitedClaim] = Field(default_factory=list, max_length=6)
    benign_or_contradictory_evidence: list[CitedClaim] = Field(default_factory=list, max_length=8)
    network_exposure: list[CitedClaim] = Field(default_factory=list, max_length=8)
    recommended_checks: list[CitedClaim] = Field(default_factory=list, max_length=8)
    limitations: list[CitedClaim] = Field(default_factory=list, max_length=8)


@dataclass(frozen=True, slots=True)
class ToolTrace:
    step: int
    tool: str
    arguments: dict[str, Any]
    status: str
    summary: str
    evidence_ids: tuple[str, ...]
    elapsed_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "tool": self.tool, "arguments": self.arguments,
                "status": self.status, "summary": self.summary,
                "evidence_ids": list(self.evidence_ids), "elapsed_ms": self.elapsed_ms}


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    report: FraudInvestigationDraft
    answer: str
    evidence: tuple[EvidenceRecord, ...]
    graph: dict[str, list[dict[str, Any]]]
    timeline: tuple[dict[str, Any], ...]
    trace: tuple[ToolTrace, ...]
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer, "report": self.report.model_dump(),
            "evidence": [record.as_dict() for record in self.evidence],
            "graph": self.graph, "timeline": list(self.timeline),
            "trace": [item.as_dict() for item in self.trace], "metrics": self.metrics,
        }


def report_claims(report: FraudInvestigationDraft) -> tuple[CitedClaim, ...]:
    return (
        report.executive_summary, report.risk_assessment, *report.observed_facts,
        *report.derived_patterns, *report.typology_matches,
        *report.benign_or_contradictory_evidence, *report.network_exposure,
        *report.recommended_checks, *report.limitations,
    )


def validate_report(report: FraudInvestigationDraft, evidence: Sequence[EvidenceRecord]) -> None:
    if not evidence:
        raise RuntimeError("A fraud assessment cannot be produced without retrieved evidence")
    valid_ids = {record.evidence_id for record in evidence}
    claims = report_claims(report)
    unknown = {item for claim in claims for item in claim.evidence_ids} - valid_ids
    if unknown:
        raise RuntimeError("Report cited unknown evidence: " + ", ".join(sorted(unknown)))
    if any(not claim.evidence_ids for claim in claims):
        raise RuntimeError("Every report claim requires an evidence citation")
    observed_ids = {record.evidence_id for record in evidence if record.kind in {"alert", "entity", "transaction", "relationship"}}
    if observed_ids and not any(observed_ids & set(claim.evidence_ids) for claim in (report.executive_summary, report.risk_assessment)):
        raise RuntimeError("Risk assessment must cite observed graph evidence")


def format_report(report: FraudInvestigationDraft) -> str:
    def cited(claim: CitedClaim) -> str:
        return claim.claim + " " + " ".join(f"[{item}]" for item in claim.evidence_ids)
    lines = [cited(report.executive_summary), "", f"Risk assessment · {report.risk_level} risk · {report.confidence} confidence", cited(report.risk_assessment)]
    sections = (
        ("Observed facts", report.observed_facts),
        ("Derived graph patterns", report.derived_patterns),
        ("Typology matches", report.typology_matches),
        ("Benign or contradictory evidence", report.benign_or_contradictory_evidence),
        ("Network exposure", report.network_exposure),
        ("Recommended human checks", report.recommended_checks),
        ("Limitations", report.limitations),
    )
    for heading, claims in sections:
        if claims:
            lines.extend(["", heading, *(f"- {cited(claim)}" for claim in claims)])
    return "\n".join(lines)


class FraudInvestigationAgent:
    def __init__(self, tools: FraudInvestigationTools, openai_client: Any, model: str, *, max_rounds: int = 6):
        self._tools = tools
        self._client = openai_client
        self._model = model
        self._max_rounds = max(3, min(int(max_rounds), 8))

    def investigate(self, question: str, *, history: Sequence[dict[str, str]] = ()) -> InvestigationResult:
        question = question.strip()
        if len(question) < 3:
            raise ValueError("Investigation question must contain at least 3 characters")
        ledger = EvidenceLedger()
        trace: list[ToolTrace] = []
        input_items: list[Any] = [{"role": "user", "content": json.dumps({"question": question, "prior_investigation_turns": list(history)[-6:]}, ensure_ascii=False)}]
        input_tokens = output_tokens = 0
        started = time.perf_counter()
        report: FraudInvestigationDraft | None = None

        for _ in range(self._max_rounds):
            response = self._client.responses.parse(
                model=self._model, reasoning={"effort": "low"},
                instructions=AGENT_INSTRUCTIONS, input=input_items,
                tools=TOOL_DEFINITIONS, text_format=FraudInvestigationDraft,
                parallel_tool_calls=False, store=False, max_output_tokens=1800,
            )
            input_tokens += int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0)
            output_tokens += int(getattr(getattr(response, "usage", None), "output_tokens", 0) or 0)
            input_items.extend(response.output)
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                report = self._parsed_report(response)
                if report is None:
                    raise RuntimeError("The model returned neither a tool call nor a report")
                break
            for call in calls:
                tool_started = time.perf_counter()
                try:
                    arguments = json.loads(call.arguments)
                    result = self._tools.execute(call.name, arguments)
                    assigned = ledger.add(result)
                    status, summary = "completed", result.summary
                    output = tool_payload(summary, assigned)
                    evidence_ids = tuple(record.evidence_id for record in assigned)
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    arguments, status, summary = {}, "rejected", str(exc)
                    output, evidence_ids = json.dumps({"error": summary, "evidence": []}), ()
                trace.append(ToolTrace(len(trace) + 1, call.name, arguments, status, summary, evidence_ids, elapsed_ms(tool_started)))
                input_items.append({"type": "function_call_output", "call_id": call.call_id, "output": output})

        if report is None:
            response = self._client.responses.parse(
                model=self._model, reasoning={"effort": "low"},
                instructions=AGENT_INSTRUCTIONS + "\nThe tool budget is exhausted. Synthesize the typed report now without another tool call.",
                input=input_items, text_format=FraudInvestigationDraft,
                store=False, max_output_tokens=1800,
            )
            input_tokens += int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0)
            output_tokens += int(getattr(getattr(response, "usage", None), "output_tokens", 0) or 0)
            report = self._parsed_report(response)
            if report is None:
                raise RuntimeError("The model did not synthesize a final fraud report")

        validate_report(report, ledger.records)
        return InvestigationResult(
            report, format_report(report), ledger.records, ledger.graph(), tuple(ledger.timeline()), tuple(trace),
            {"total_ms": int((time.perf_counter() - started) * 1000), "tool_calls": len(trace),
             "agent_rounds": min(self._max_rounds, len(trace) + 1), "evidence_count": len(ledger.records),
             "input_tokens": input_tokens, "output_tokens": output_tokens, "grounding_review": "passed"},
        )

    @staticmethod
    def _parsed_report(response: Any) -> FraudInvestigationDraft | None:
        parsed = getattr(response, "output_parsed", None)
        if isinstance(parsed, FraudInvestigationDraft):
            return parsed
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            return None
        try:
            return FraudInvestigationDraft.model_validate_json(output_text)
        except ValueError as exc:
            raise RuntimeError("The model returned an invalid report structure") from exc
