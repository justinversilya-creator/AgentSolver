from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_URL_LENGTH = 2048


class SupportStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIED = "unverified"


class RetrievalStatus(str, Enum):
    METADATA_ONLY = "metadata_only"
    CONTENT_RETRIEVED = "content_retrieved"
    FAILED = "failed"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNDETERMINED = "undetermined"


def coerce_http_url(value: Any) -> str | None:
    """Keep only well-formed http/https URLs. Anything else becomes None. URLs are never guessed."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > MAX_URL_LENGTH:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return candidate


def coerce_support_status(value: Any) -> str:
    """Keep a known label; anything else becomes 'unverified'. Status is never upgraded here."""
    allowed = {status.value for status in SupportStatus}
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return SupportStatus.UNVERIFIED.value


class SourceRef(BaseModel):
    """Public source reference used in the final report."""

    title: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    publication_date: str | None = Field(default=None, max_length=50)

    @field_validator("url", mode="before")
    @classmethod
    def check_url(cls, value: Any) -> str | None:
        return coerce_http_url(value)


class KeyFinding(BaseModel):
    """A claim with the source it rests on and its validation status."""

    claim: str = Field(..., min_length=1, max_length=2000)
    source_title: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    support_status: SupportStatus = SupportStatus.UNVERIFIED
    supporting_excerpt: str | None = Field(default=None, max_length=2000)
    validation_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("source_url", mode="before")
    @classmethod
    def check_source_url(cls, value: Any) -> str | None:
        return coerce_http_url(value)

    @field_validator("support_status", mode="before")
    @classmethod
    def check_support_status(cls, value: Any) -> str:
        return coerce_support_status(value)


class ValidationResult(BaseModel):
    """Result of checking one claim against its source record."""

    claim: str = Field(..., min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    url_accessible: bool | None = None
    support_status: SupportStatus = SupportStatus.UNVERIFIED
    supporting_excerpt: str | None = Field(default=None, max_length=2000)
    validation_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("source_url", mode="before")
    @classmethod
    def check_source_url(cls, value: Any) -> str | None:
        return coerce_http_url(value)

    @field_validator("support_status", mode="before")
    @classmethod
    def check_support_status(cls, value: Any) -> str:
        return coerce_support_status(value)


class ResearchSource(BaseModel):
    """
    A source returned by the search provider.
    retrieval_status shows whether only metadata was returned or the content was actually fetched.
    """

    model_config = ConfigDict(use_enum_values=False)

    source_id: str = Field(..., pattern=r"^S\d+$", max_length=10)
    title: str = Field(..., min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    publisher: str | None = Field(default=None, max_length=300)
    publication_date: str | None = Field(default=None, max_length=50)
    authors: list[str] = Field(default_factory=list, max_length=50)
    doi: str | None = Field(default=None, max_length=200)
    retrieved_excerpt: str | None = Field(default=None, max_length=5000)
    retrieval_status: RetrievalStatus = RetrievalStatus.METADATA_ONLY
    metadata_returned: bool = True
    content_retrieved: bool = False
    claims_supported: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("url", mode="before")
    @classmethod
    def check_url(cls, value: Any) -> str | None:
        return coerce_http_url(value)


class ResearchFinding(BaseModel):
    """A finding from the Research Agent, linked to one or more source IDs."""

    finding_id: str = Field(..., pattern=r"^F\d+$", max_length=10)
    claim: str = Field(..., min_length=1, max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    confidence: Confidence = Confidence.UNDETERMINED
    limitations: list[str] = Field(default_factory=list, max_length=50)


class ResearchResult(BaseModel):
    """Validated output of the Research Agent."""

    agent: str = Field(default="research", pattern=r"^research$")
    question: str = Field(..., min_length=1, max_length=500)
    key_findings: list[ResearchFinding] = Field(default_factory=list, max_length=100)
    sources: list[ResearchSource] = Field(default_factory=list, max_length=200)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=50)
    conflicting_findings: list[str] = Field(default_factory=list, max_length=50)
    research_limitations: list[str] = Field(default_factory=list, max_length=50)