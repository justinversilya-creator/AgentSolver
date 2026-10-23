# backend/agents/solution_agent.py
"""
Solution Agent: proposes practical approaches grounded in the Research Agent's output.

Proposals come from an injected proposer (for example, an LLM call through JsonLLMClient).
This module never invents sources. Every proposal is checked here:
- Cited source IDs must exist in the Research Agent output. Unknown IDs are removed.
- Evidence strength is capped by the number of sources with retrieved content.
  This agent never reports "strong", because the Validation Agent has not run yet.
- Wording that overstates the evidence is flagged for review.
If no proposer is configured, or the proposer fails, the result explains why and contains no proposals.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.schemas.evidence import ResearchResult, RetrievalStatus
from backend.schemas.solution import EvidenceStrength, ProposedSolution, SolutionResult

logger = logging.getLogger("agentsolve.solution")

MAX_SOLUTIONS = 4
MAX_DRAFT_SOLUTIONS = 10
MAX_QUESTION_CHARS = 500
COMPARISON_CRITERIA = [
    "Strength of supporting evidence",
    "Practical feasibility",
    "Implementation requirements",
    "Risks and unintended consequences",
]
OVERSTATED_WORDING = re.compile(
    r"\b(proven|proves|guaranteed|definitively|tested|clinically validated)\b", re.IGNORECASE
)
_RANK = {
    EvidenceStrength.INSUFFICIENT: 0,
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.STRONG: 3,
}

SYSTEM_PROMPT = """You are the Solution Agent of AgentSolve AI.
Propose two to four practical approaches to the question, using only the research provided.
Cite only source IDs that appear in research.sources. Never invent sources, URLs, statistics or findings.
Do not claim any approach has been tested or proven. Separate evidence from assumptions.
Return only one JSON object with keys: solutions (list), tradeoffs (list of strings),
additional_evidence_needed (list of strings), unresolved_questions (list of strings).
Each solution has: name, description, benefits, requirements, limitations, risks,
supporting_source_ids, assumptions, evidence_strength (strong | moderate | weak | insufficient)."""


class ProposerError(Exception):
    """Raised by a proposer when proposal generation fails."""


class JsonLLMClient(Protocol):
    """Interface for an LLM client that returns a JSON object. Implementations must be asynchronous."""

    async def complete_json(self, system: str, user: str) -> Mapping[str, Any]:
        """Return the parsed JSON object. Raise ProposerError on failure."""
        ...


class SolutionProposer(Protocol):
    """Interface for anything that proposes solutions from validated research."""

    async def propose(self, question: str, research: ResearchResult) -> Mapping[str, Any]:
        """Return a mapping with a 'solutions' list and optional string-list fields."""
        ...


class LLMSolutionProposer:
    """Builds the prompt from validated research only and delegates the call to a JSON LLM client."""

    def __init__(self, client: JsonLLMClient) -> None:
        self._client = client

    async def propose(self, question: str, research: ResearchResult) -> Mapping[str, Any]:
        user_prompt = json.dumps(
            {"question": question, "research": research.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        )
        return await self._client.complete_json(SYSTEM_PROMPT, user_prompt)


class DraftSolution(BaseModel):
    """A proposal as returned by the proposer, before the agent checks it against the research."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    benefits: list[str] = Field(default_factory=list, max_length=20)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    supporting_source_ids: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    evidence_strength: str = EvidenceStrength.INSUFFICIENT.value

    @field_validator("evidence_strength", mode="before")
    @classmethod
    def coerce_strength(cls, value: Any) -> str:
        allowed = {strength.value for strength in EvidenceStrength}
        if isinstance(value, str) and value.strip().lower() in allowed:
            return value.strip().lower()
        return EvidenceStrength.INSUFFICIENT.value


class SolutionAgent:
    """Runs the proposer and returns a validated SolutionResult."""

    def __init__(self, proposer: SolutionProposer | None = None) -> None:
        self._proposer = proposer

    async def run(
        self,
        question: str,
        research: ResearchResult | Mapping[str, Any] | None,
        request_id: str,
    ) -> SolutionResult:
        """
        Build proposals from the Research Agent output.
        Missing, invalid, or empty research never raises. It returns a result that explains the gap.
        Raises ValueError only if the question itself is empty or too long.
        """
        clean_question = " ".join(question.split())
        if not clean_question:
            raise ValueError("A research question is required.")
        if len(clean_question) > MAX_QUESTION_CHARS:
            raise ValueError("The research question is too long.")

        research_model, problem = _parse_research(research)
        if research_model is None:
            return _empty_result(
                clean_question,
                "No usable Research Agent output was supplied, so the problem cannot be defined from evidence in this run.",
                ["A valid Research Agent output with at least one source."],
                [problem or "No Research Agent output was supplied."],
            )

        summary = _problem_summary(clean_question, research_model)

        if not research_model.sources and not research_model.key_findings:
            return _empty_result(
                clean_question,
                summary,
                ["Research Agent output with at least one source and one finding."],
                ["The Research Agent returned no sources or findings, so no solution can be grounded in evidence."],
            )

        if self._proposer is None:
            return _empty_result(
                clean_question,
                summary,
                ["A configured solution proposer."],
                ["No solution proposer is configured. No proposals were generated."],
            )

        try:
            payload = await self._proposer.propose(clean_question, research_model)
        except ProposerError:
            logger.warning("Solution proposer failed (request_id=%s)", request_id)
            return _empty_result(
                clean_question,
                summary,
                ["A working solution proposer."],
                ["The solution proposer failed. No proposals were generated."],
            )

        drafts, parse_notes, tradeoffs, extra_needed, unresolved = _parse_payload(payload)
        solutions, build_notes = _build_solutions(drafts, research_model)

        additional = list(extra_needed)
        if solutions:
            additional.append("Validation Agent results for every claim cited by a proposal before comparing solutions.")
        if not any(s.evidence_strength is not EvidenceStrength.INSUFFICIENT for s in solutions):
            additional.append("Retrieved content (abstracts or full text) for the sources cited by proposals.")

        return SolutionResult(
            agent="solution",
            question=clean_question,
            problem_summary=summary,
            proposed_solutions=solutions,
            comparison_criteria=COMPARISON_CRITERIA if len(solutions) >= 2 else [],
            tradeoffs=tradeoffs,
            additional_evidence_needed=_unique(additional)[:20],
            unresolved_questions=_unique(parse_notes + build_notes + unresolved)[:20],
        )


def _parse_research(
    research: ResearchResult | Mapping[str, Any] | None,
) -> tuple[ResearchResult | None, str | None]:
    if research is None:
        return None, "No Research Agent output was supplied."
    if isinstance(research, ResearchResult):
        return research, None
    if isinstance(research, Mapping):
        try:
            return ResearchResult.model_validate(dict(research)), None
        except ValidationError:
            return None, "The Research Agent output was invalid and could not be used."
    return None, "The Research Agent output had an unsupported type."


def _problem_summary(question: str, research: ResearchResult) -> str:
    total = len(research.sources)
    with_content = sum(
        1 for s in research.sources if s.retrieval_status is RetrievalStatus.CONTENT_RETRIEVED
    )
    summary = (
        f"Question: {question} The Research Agent returned {total} source(s), "
        f"{with_content} with retrieved content, and {len(research.key_findings)} finding(s). "
        "Proposals are limited to these sources."
    )
    return summary[:2000]


def _cap_strength(
    requested: EvidenceStrength,
    source_ids: list[str],
    sources_by_id: Mapping[str, Any],
) -> EvidenceStrength:
    """
    Cap strength by retrieved content. Zero retrieved sources means insufficient,
    one means weak, two or more means moderate. Never strong before validation.
    """
    with_content = [
        sources_by_id[i] for i in source_ids
        if sources_by_id[i].retrieval_status is RetrievalStatus.CONTENT_RETRIEVED
    ]
    if not with_content:
        ceiling = EvidenceStrength.INSUFFICIENT
    elif len(with_content) == 1:
        ceiling = EvidenceStrength.WEAK
    else:
        ceiling = EvidenceStrength.MODERATE
    return min(requested, ceiling, key=_RANK.__getitem__)


def _build_solutions(
    drafts: list[DraftSolution],
    research: ResearchResult,
) -> tuple[list[ProposedSolution], list[str]]:
    sources_by_id = {s.source_id: s for s in research.sources}
    solutions: list[ProposedSolution] = []
    notes: list[str] = []

    for draft in drafts[:MAX_SOLUTIONS]:
        cited = _unique(draft.supporting_source_ids)
        valid = [i for i in cited if i in sources_by_id]
        unknown = [i for i in cited if i not in sources_by_id]

        limitations = list(draft.limitations)
        if unknown:
            limitations.append(
                "Removed source references not present in the Research Agent output: " + ", ".join(unknown) + "."
            )
        if not valid:
            limitations.append("No supporting source from the Research Agent output. Treat this as an unsupported idea.")

        text = f"{draft.name} {draft.description}"
        if OVERSTATED_WORDING.search(text):
            limitations.append("Wording may overstate the evidence. Review before relying on it.")

        requested = EvidenceStrength(draft.evidence_strength)
        strength = _cap_strength(requested, valid, sources_by_id)
        if strength is not requested:
            limitations.append(
                f"Evidence strength was lowered from {requested.value} to {strength.value} based on retrieved content."
            )

        solutions.append(
            ProposedSolution(
                solution_id=f"SOL{len(solutions) + 1}",
                name=draft.name,
                description=draft.description,
                benefits=draft.benefits,
                requirements=draft.requirements,
                limitations=limitations[:20],
                risks=draft.risks,
                supporting_source_ids=valid,
                assumptions=draft.assumptions,
                evidence_strength=strength,
            )
        )

    if len(drafts) > MAX_SOLUTIONS:
        notes.append(f"{len(drafts) - MAX_SOLUTIONS} proposal(s) were omitted to keep the output to {MAX_SOLUTIONS}.")

    return solutions, notes


def _parse_payload(
    payload: Mapping[str, Any],
) -> tuple[list[DraftSolution], list[str], list[str], list[str], list[str]]:
    if not isinstance(payload, Mapping):
        return [], ["The proposer returned an unexpected format. No proposals were used."], [], [], []

    raw_solutions = payload.get("solutions")
    notes: list[str] = []
    if not isinstance(raw_solutions, list):
        notes.append("The proposer returned no solutions list.")
        raw_solutions = []

    drafts: list[DraftSolution] = []
    malformed = 0
    for item in raw_solutions[:MAX_DRAFT_SOLUTIONS]:
        try:
            drafts.append(DraftSolution.model_validate(item))
        except ValidationError:
            malformed += 1
    if malformed:
        notes.append(f"{malformed} malformed proposal(s) were removed.")

    return (
        drafts,
        notes,
        _str_list(payload.get("tradeoffs")),
        _str_list(payload.get("additional_evidence_needed")),
        _str_list(payload.get("unresolved_questions")),
    )


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip()[:500] for item in value if isinstance(item, str) and item.strip()][:20]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _empty_result(
    question: str,
    problem_summary: str,
    additional: list[str],
    unresolved: list[str],
) -> SolutionResult:
    return SolutionResult(
        agent="solution",
        question=question,
        problem_summary=problem_summary[:2000],
        proposed_solutions=[],
        comparison_criteria=[],
        tradeoffs=[],
        additional_evidence_needed=additional,
        unresolved_questions=unresolved,
    )q