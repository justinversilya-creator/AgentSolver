from enum import Enum

from pydantic import BaseModel, Field

from backend.schemas.evidence import KeyFinding, SourceRef, ValidationResult


class ResearchStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DEMO = "demo"


class Solution(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    supporting_study_titles: list[str] = Field(default_factory=list, max_length=20)


class ReportBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    executive_summary: str | None = Field(default=None, max_length=5000)
    key_findings: list[KeyFinding] = Field(default_factory=list, max_length=50)
    sources: list[SourceRef] = Field(default_factory=list, max_length=100)
    solutions: list[Solution] = Field(default_factory=list, max_length=20)
    counterarguments: list[str] = Field(default_factory=list, max_length=50)
    validation_results: list[ValidationResult] = Field(default_factory=list, max_length=100)
    recommendation: str | None = Field(default=None, max_length=3000)
    uncertainty: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=50)


class ResearchResponse(BaseModel):
    request_id: str
    status: ResearchStatus
    demo: bool = False
    report: ReportBody