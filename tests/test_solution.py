# tests/test_solution_agent.py
import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest

from backend.agents.solution_agent import (
    LLMSolutionProposer,
    ProposerError,
    SolutionAgent,
)
from backend.schemas.evidence import ResearchResult, ResearchSource, RetrievalStatus
from backend.schemas.solution import EvidenceStrength, SolutionResult

QUESTION = "Does spaced repetition improve long-term retention compared with massed practice?"


def make_source(index: int, status: RetrievalStatus = RetrievalStatus.CONTENT_RETRIEVED) -> ResearchSource:
    has_content = status is RetrievalStatus.CONTENT_RETRIEVED
    return ResearchSource(
        source_id=f"S{index}",
        title=f"Study {index}",
        url=f"https://example.org/study-{index}",
        retrieved_excerpt=f"Excerpt from study {index}." if has_content else None,
        retrieval_status=status,
        content_retrieved=has_content,
    )


def make_research(sources=None, findings=None) -> ResearchResult:
    return ResearchResult(
        agent="research",
        question=QUESTION,
        key_findings=findings or [],
        sources=sources or [],
    )


def make_research_with_findings(*sources: ResearchSource) -> ResearchResult:
    from backend.schemas.evidence import ResearchFinding

    findings = [
        ResearchFinding(finding_id=f"F{i}", claim=f"Claim from {s.source_id}.", source_ids=[s.source_id])
        for i, s in enumerate(sources, start=1)
    ]
    return make_research(sources=list(sources), findings=findings)


def draft(name="Spaced schedule", source_ids=None, strength="moderate", **extra) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} description.",
        "benefits": ["Benefit."],
        "requirements": ["Requirement."],
        "limitations": [],
        "risks": ["Risk."],
        "supporting_source_ids": source_ids if source_ids is not None else ["S1"],
        "assumptions": ["Assumption."],
        "evidence_strength": strength,
        **extra,
    }


class FakeProposer:
    """Test double for a proposer. Returns a preset payload and never calls a network service."""

    def __init__(self, payload: Mapping[str, Any] | None = None, error: Exception | None = None) -> None:
        self._payload = payload or {"solutions": []}
        self._error = error
        self.calls = 0

    async def propose(self, question, research):
        self.calls += 1
        if self._error:
            raise self._error
        return self._payload


class FakeLLMClient:
    """Mock JSON LLM client. Records prompts and returns a preset JSON object."""

    def __init__(self, response: Mapping[str, Any] | None = None, error: Exception | None = None) -> None:
        self._response = response or {"solutions": []}
        self._error = error
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    async def complete_json(self, system: str, user: str):
        self.system_prompts.append(system)
        self.user_prompts.append(user)
        if self._error:
            raise self._error
        return self._response


def run(agent: SolutionAgent, research, question: str = QUESTION) -> SolutionResult:
    return asyncio.run(agent.run(question, research, "req-1"))


def test_valid_input_returns_solutions_with_stable_ids_and_source_links():
    research = make_research_with_findings(make_source(1), make_source(2))
    proposer = FakeProposer({"solutions": [
        draft("Spaced schedule", ["S1", "S2"], strength="moderate"),
        draft("Retrieval practice", ["S2"], strength="weak"),
    ]})

    result = run(SolutionAgent(proposer), research)

    assert result.agent == "solution"
    assert [s.solution_id for s in result.proposed_solutions] == ["SOL1", "SOL2"]
    assert result.proposed_solutions[0].supporting_source_ids == ["S1", "S2"]
    assert result.proposed_solutions[0].evidence_strength is EvidenceStrength.MODERATE
    assert result.proposed_solutions[1].evidence_strength is EvidenceStrength.WEAK
    assert result.comparison_criteria
    assert proposer.calls == 1


def test_strong_is_never_reported_before_validation():
    research = make_research_with_findings(make_source(1), make_source(2), make_source(3))
    proposer = FakeProposer({"solutions": [draft(source_ids=["S1", "S2", "S3"], strength="strong")]})

    result = run(SolutionAgent(proposer), research)

    assert result.proposed_solutions[0].evidence_strength is EvidenceStrength.MODERATE
    assert any("lowered from strong to moderate" in lim for lim in result.proposed_solutions[0].limitations)


def test_single_retrieved_source_caps_strength_at_weak():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({"solutions": [draft(source_ids=["S1"], strength="moderate")]})

    result = run(SolutionAgent(proposer), research)

    assert result.proposed_solutions[0].evidence_strength is EvidenceStrength.WEAK


def test_metadata_only_sources_cap_strength_at_insufficient():
    research = make_research(sources=[make_source(1, RetrievalStatus.METADATA_ONLY)])
    proposer = FakeProposer({"solutions": [draft(source_ids=["S1"], strength="strong")]})

    result = run(SolutionAgent(proposer), research)

    assert result.proposed_solutions[0].evidence_strength is EvidenceStrength.INSUFFICIENT
    assert any("Retrieved content" in item for item in result.additional_evidence_needed)


def test_missing_research_returns_structured_result_without_calling_proposer():
    proposer = FakeProposer({"solutions": [draft()]})

    result = run(SolutionAgent(proposer), None)

    assert result.proposed_solutions == []
    assert result.problem_summary.startswith("No usable Research Agent output")
    assert "No Research Agent output was supplied." in result.unresolved_questions
    assert proposer.calls == 0


def test_invalid_research_mapping_is_reported_without_raw_error_text():
    proposer = FakeProposer({"solutions": [draft()]})

    result = run(SolutionAgent(proposer), {"agent": "wrong", "question": ""})

    assert result.proposed_solutions == []
    assert "The Research Agent output was invalid and could not be used." in result.unresolved_questions
    assert proposer.calls == 0


def test_valid_research_mapping_is_accepted():
    research = make_research_with_findings(make_source(1), make_source(2))
    mapping = research.model_dump(mode="json")
    proposer = FakeProposer({"solutions": [draft(source_ids=["S1", "S2"])]})

    result = run(SolutionAgent(proposer), mapping)

    assert len(result.proposed_solutions) == 1
    assert proposer.calls == 1


def test_empty_sources_and_findings_skip_proposer():
    proposer = FakeProposer({"solutions": [draft()]})

    result = run(SolutionAgent(proposer), make_research())

    assert result.proposed_solutions == []
    assert any("no sources or findings" in item for item in result.unresolved_questions)
    assert proposer.calls == 0


def test_missing_proposer_returns_explicit_limitation():
    result = run(SolutionAgent(proposer=None), make_research_with_findings(make_source(1)))

    assert result.proposed_solutions == []
    assert any("No solution proposer is configured" in item for item in result.unresolved_questions)


def test_proposer_error_does_not_leak_exception_text():
    proposer = FakeProposer(error=ProposerError("secret-token-abc123"))

    result = run(SolutionAgent(proposer), make_research_with_findings(make_source(1)))

    assert result.proposed_solutions == []
    assert "The solution proposer failed. No proposals were generated." in result.unresolved_questions
    assert "secret-token-abc123" not in json.dumps(result.model_dump(mode="json"))


def test_unknown_source_ids_are_removed_and_reported():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({"solutions": [draft(source_ids=["S1", "S99"])]})

    result = run(SolutionAgent(proposer), research)

    solution = result.proposed_solutions[0]
    assert solution.supporting_source_ids == ["S1"]
    assert any("S99" in lim for lim in solution.limitations)


def test_unsupported_proposal_is_kept_only_as_flagged_idea():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({"solutions": [draft(source_ids=["S42"], strength="strong")]})

    result = run(SolutionAgent(proposer), research)

    solution = result.proposed_solutions[0]
    assert solution.supporting_source_ids == []
    assert solution.evidence_strength is EvidenceStrength.INSUFFICIENT
    assert any("unsupported idea" in lim for lim in solution.limitations)


def test_overstated_wording_is_flagged_not_silently_kept():
    research = make_research_with_findings(make_source(1), make_source(2))
    proposer = FakeProposer({"solutions": [
        draft("Proven method", ["S1", "S2"], description_override=None)
    ]})
    proposer._payload["solutions"][0]["description"] = "This method is proven to work."

    result = run(SolutionAgent(proposer), research)

    assert any("overstate" in lim for lim in result.proposed_solutions[0].limitations)


def test_more_than_four_proposals_are_truncated_with_note():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({"solutions": [draft(f"Option {i}") for i in range(6)]})

    result = run(SolutionAgent(proposer), research)

    assert len(result.proposed_solutions) == 4
    assert any("2 proposal(s) were omitted" in item for item in result.unresolved_questions)


def test_malformed_proposal_is_dropped_and_others_kept():
    research = make_research_with_findings(make_source(1))
    bad = {"description": "No name here."}
    proposer = FakeProposer({"solutions": [bad, draft("Good option")]})

    result = run(SolutionAgent(proposer), research)

    assert [s.name for s in result.proposed_solutions] == ["Good option"]
    assert any("malformed proposal" in item for item in result.unresolved_questions)


def test_unknown_strength_label_becomes_insufficient():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({"solutions": [draft(strength="very high")]})

    result = run(SolutionAgent(proposer), research)

    assert result.proposed_solutions[0].evidence_strength is EvidenceStrength.INSUFFICIENT


def test_comparison_criteria_only_when_two_or_more_solutions():
    research = make_research_with_findings(make_source(1))

    single = run(SolutionAgent(FakeProposer({"solutions": [draft()]})), research)
    double = run(SolutionAgent(FakeProposer({"solutions": [draft("A"), draft("B")]})), research)

    assert single.comparison_criteria == []
    assert double.comparison_criteria


def test_tradeoffs_and_unresolved_questions_come_only_from_proposer():
    research = make_research_with_findings(make_source(1))
    proposer = FakeProposer({
        "solutions": [draft()],
        "tradeoffs": ["Higher effort for learners."],
        "unresolved_questions": ["Effect in older adults is unknown."],
    })

    result = run(SolutionAgent(proposer), research)

    assert result.tradeoffs == ["Higher effort for learners."]
    assert "Effect in older adults is unknown." in result.unresolved_questions


def test_empty_question_raises_value_error():
    with pytest.raises(ValueError):
        run(SolutionAgent(FakeProposer()), make_research_with_findings(make_source(1)), question="   ")


def test_llm_proposer_sends_only_validated_research_and_returns_client_output():
    research = make_research_with_findings(make_source(1), make_source(2))
    client = FakeLLMClient({"solutions": [draft(source_ids=["S1"])]})

    result = run(SolutionAgent(LLMSolutionProposer(client)), research)

    assert len(result.proposed_solutions) == 1
    assert len(client.user_prompts) == 1
    sent = json.loads(client.user_prompts[0])
    assert sent["question"] == QUESTION
    assert [s["source_id"] for s in sent["research"]["sources"]] == ["S1", "S2"]
    assert "Do not claim any approach has been tested or proven" in client.system_prompts[0]


def test_llm_client_error_is_handled_as_proposer_failure():
    client = FakeLLMClient(error=ProposerError("upstream failure"))

    result = run(SolutionAgent(LLMSolutionProposer(client)), make_research_with_findings(make_source(1)))

    assert result.proposed_solutions == []
    assert "The solution proposer failed. No proposals were generated." in result.unresolved_questions