# backend/schemas/solution.py
"""Schemas for the Solution Agent output. Source IDs must come from the Research Agent."""

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class ProposedSolution(BaseModel):
    """One proposed approach. Its claims are linked to Research Agent source IDs where possible."""

    solution_id: str = Field(..., pattern=r"^SOL\d+$", max_length=10)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    benefits: list[str] = Field(default_factory=list, max_length=20)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    supporting_source_ids: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    evidence_strength: EvidenceStrength = EvidenceStrength.INSUFFICIENT


class SolutionResult(BaseModel):
    """Validated output of the Solution Agent."""

    agent: str = Field(default="solution", pattern=r"^solution$")
    question: str = Field(..., min_length=1, max_length=500)
    problem_summary: str = Field(..., min_length=1, max_length=2000)
    proposed_solutions: list[ProposedSolution] = Field(default_factory=list, max_length=4)
    comparison_criteria: list[str] = Field(default_factory=list, max_length=10)
    tradeoffs: list[str] = Field(default_factory=list, max_length=20)
    additional_evidence_needed: list[str] = Field(default_factory=list, max_length=20)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)