"""Bounded OpenAI tool loop and citation-validated incident report synthesis."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from evidence import EvidenceLedger, EvidenceRecord
from tools import InvestigationTools, TOOL_DEFINITIONS, elapsed_ms, tool_payload


AGENT_INSTRUCTIONS = """
You are a read-only incident investigator for the fictional Northstar Commerce
platform. Investigate by calling the supplied tools before reaching a
conclusion. Prefer exact graph facts for incidents, topology, alerts, and
deployments; use hybrid document retrieval for runbooks and historical
postmortems. Test more than one plausible hypothesis when the evidence permits.

Every factual claim in the final report must reference evidence IDs returned by
tools. Put IDs only in each claim's evidence_ids field; never write citation
brackets inside claim text. Keep observed impact distinct from topology-only exposure. Keep facts
distinct from hypotheses. A deployment before an incident is correlation, not
causation, unless telemetry or historical evidence strengthens it. Never invent
an ID, metric, relationship, action, or source. When evidence is insufficient,
say exactly what is missing. You may propose safe diagnostic checks, but you
cannot execute changes, rollbacks, commands, or external actions.

Use no more tool calls than necessary. The application enforces hop, result,
and investigation-round limits. Return the typed report once the evidence is
sufficient or the bounded investigation cannot make further progress.
""".strip()


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=3, max_length=600)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class InvestigationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=160)
    summary: CitedClaim
    leading_hypothesis: CitedClaim
    confidence: Literal["low", "moderate", "high"]
    supporting_evidence: list[CitedClaim] = Field(default_factory=list, max_length=8)
    contradicting_evidence: list[CitedClaim] = Field(default_factory=list, max_length=6)
    blast_radius: list[CitedClaim] = Field(default_factory=list, max_length=8)
    next_checks: list[CitedClaim] = Field(default_factory=list, max_length=6)
    limitations: list[CitedClaim] = Field(default_factory=list, max_length=6)


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
        return {
            "step": self.step,
            "tool": self.tool,
            "arguments": self.arguments,
            "status": self.status,
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    report: InvestigationDraft
    answer: str
    evidence: tuple[EvidenceRecord, ...]
    graph: dict[str, list[dict[str, Any]]]
    timeline: tuple[dict[str, Any], ...]
    trace: tuple[ToolTrace, ...]
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "report": self.report.model_dump(),
            "evidence": [record.as_dict() for record in self.evidence],
            "graph": self.graph,
            "timeline": list(self.timeline),
            "trace": [item.as_dict() for item in self.trace],
            "metrics": self.metrics,
        }


def validate_report(report: InvestigationDraft, evidence: Sequence[EvidenceRecord]) -> None:
    valid_ids = {record.evidence_id for record in evidence}
    claims = (
        report.summary,
        report.leading_hypothesis,
        *report.supporting_evidence,
        *report.contradicting_evidence,
        *report.blast_radius,
        *report.next_checks,
        *report.limitations,
    )
    used = {evidence_id for claim in claims for evidence_id in claim.evidence_ids}
    unknown = used - valid_ids
    if unknown:
        raise RuntimeError(
            "Report cited unknown evidence: " + ", ".join(sorted(unknown))
        )
    if evidence and any(not claim.evidence_ids for claim in claims):
        raise RuntimeError("Every report claim requires an evidence citation")
    if evidence and not used:
        raise RuntimeError("Report did not cite the investigation evidence")


def format_report(report: InvestigationDraft) -> str:
    def cited(claim: CitedClaim) -> str:
        return claim.claim + " " + " ".join(
            f"[{evidence_id}]" for evidence_id in claim.evidence_ids
        )

    lines = [
        cited(report.summary),
        "",
        f"Leading hypothesis ({report.confidence} confidence)",
        cited(report.leading_hypothesis),
    ]
    sections = (
        ("Supporting evidence", report.supporting_evidence),
        ("Contradicting evidence", report.contradicting_evidence),
        ("Blast radius", report.blast_radius),
    )
    for heading, claims in sections:
        if not claims:
            continue
        lines.extend(["", heading])
        lines.extend(f"- {cited(claim)}" for claim in claims)
    if report.next_checks:
        lines.extend(["", "Next safe checks"])
        lines.extend(f"- {cited(item)}" for item in report.next_checks)
    if report.limitations:
        lines.extend(["", "Limitations"])
        lines.extend(f"- {cited(item)}" for item in report.limitations)
    return "\n".join(lines)


class IncidentInvestigationAgent:
    def __init__(
        self,
        tools: InvestigationTools,
        openai_client: Any,
        model: str,
        *,
        max_rounds: int = 5,
    ):
        self._tools = tools
        self._client = openai_client
        self._model = model
        self._max_rounds = max(2, min(int(max_rounds), 8))

    def investigate(
        self,
        question: str,
        *,
        history: Sequence[dict[str, str]] = (),
    ) -> InvestigationResult:
        question = question.strip()
        if len(question) < 3:
            raise ValueError("Investigation question must contain at least 3 characters")

        ledger = EvidenceLedger()
        trace: list[ToolTrace] = []
        input_items: list[Any] = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "prior_investigation_turns": list(history)[-6:],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        input_tokens = 0
        output_tokens = 0
        started = time.perf_counter()
        report: InvestigationDraft | None = None

        for round_index in range(1, self._max_rounds + 1):
            response = self._client.responses.parse(
                model=self._model,
                reasoning={"effort": "low"},
                instructions=AGENT_INSTRUCTIONS,
                input=input_items,
                tools=TOOL_DEFINITIONS,
                text_format=InvestigationDraft,
                parallel_tool_calls=False,
                store=False,
                max_output_tokens=1400,
            )
            input_tokens += int(
                getattr(getattr(response, "usage", None), "input_tokens", 0) or 0
            )
            output_tokens += int(
                getattr(getattr(response, "usage", None), "output_tokens", 0) or 0
            )
            input_items.extend(response.output)
            function_calls = [
                item for item in response.output if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                report = self._parsed_report(response)
                if report is None:
                    raise RuntimeError("The model returned neither a tool call nor a report")
                break

            for call in function_calls:
                tool_started = time.perf_counter()
                try:
                    arguments = json.loads(call.arguments)
                    result = self._tools.execute(call.name, arguments)
                    assigned = ledger.add(result)
                    status = "completed"
                    summary = result.summary
                    output = tool_payload(summary, assigned)
                    evidence_ids = tuple(record.evidence_id for record in assigned)
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    arguments = {}
                    status = "rejected"
                    summary = str(exc)
                    output = json.dumps({"error": summary, "evidence": []})
                    evidence_ids = ()
                trace.append(
                    ToolTrace(
                        step=len(trace) + 1,
                        tool=call.name,
                        arguments=arguments,
                        status=status,
                        summary=summary,
                        evidence_ids=evidence_ids,
                        elapsed_ms=elapsed_ms(tool_started),
                    )
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )

        if report is None:
            response = self._client.responses.parse(
                model=self._model,
                reasoning={"effort": "low"},
                instructions=(
                    AGENT_INSTRUCTIONS
                    + "\nThe investigation budget is exhausted. Synthesize the typed report now; do not request another tool."
                ),
                input=input_items,
                text_format=InvestigationDraft,
                store=False,
                max_output_tokens=1400,
            )
            input_tokens += int(
                getattr(getattr(response, "usage", None), "input_tokens", 0) or 0
            )
            output_tokens += int(
                getattr(getattr(response, "usage", None), "output_tokens", 0) or 0
            )
            report = self._parsed_report(response)
            if report is None:
                raise RuntimeError("The model did not synthesize a final incident report")

        validate_report(report, ledger.records)
        return InvestigationResult(
            report=report,
            answer=format_report(report),
            evidence=ledger.records,
            graph=ledger.graph(),
            timeline=tuple(ledger.timeline()),
            trace=tuple(trace),
            metrics={
                "total_ms": int((time.perf_counter() - started) * 1000),
                "tool_calls": len(trace),
                "agent_rounds": min(self._max_rounds, len(trace) + 1),
                "evidence_count": len(ledger.records),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

    @staticmethod
    def _parsed_report(response: Any) -> InvestigationDraft | None:
        parsed = getattr(response, "output_parsed", None)
        if isinstance(parsed, InvestigationDraft):
            return parsed
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            return None
        try:
            return InvestigationDraft.model_validate_json(output_text)
        except ValueError as exc:
            raise RuntimeError("The model returned an invalid report structure") from exc
