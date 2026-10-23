import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def new_request_id() -> str:
    return uuid.uuid4().hex


def resolve_request_id(candidate: str | None) -> str:
    """Keep a client-supplied request ID if it is safe; otherwise generate one."""
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_request_id()


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Research question, 10 to 500 characters after trimming.",
        examples=["How effective is spaced repetition for student learning?"],
    )
    request_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional client-generated ID. Letters, digits, '-' and '_' only.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def clean_question(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Question must be a string.")
        return CONTROL_CHARS.sub("", value).strip()