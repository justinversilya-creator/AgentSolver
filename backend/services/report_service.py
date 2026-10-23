import re
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.schemas.evidence import KeyFinding, SourceRef, ValidationResult
from backend.schemas.report import ReportBody, ResearchResponse, ResearchStatus, Solution
from backend.utils.errors import InvalidWorkflowResponseError, WorkflowFailedError

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_DEPTH = 8
MAX_ITEMS = 50

SUCCESS_STATUSES = {
    ResearchStatus.COMPLETED.value,
    ResearchStatus.PARTIAL.value,
    ResearchStatus.INSUFFICIENT_EVIDENCE.value,
}
FAILURE_STATUSES = {"failed", "error"}


def _clean(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise InvalidWorkflowResponseError("The workflow response is nested too deeply.")
    if isinstance(value, str):
        return CONTROL_CHARS.sub("", value).strip()
    if isinstance(value, list):
        return [_clean(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {str(key): _clean(item, depth + 1) for key, item in value.items()}
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)][:MAX_ITEMS]


def _str_items(value: Any) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str) and item.strip()][:MAX_ITEMS]


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _valid_models(model: type[BaseModel], items: list[dict[str, Any]]) -> list[Any]:
    """Validate each item separately. Malformed items are dropped, not invented or repaired."""
    valid = []
    for item in items:
        try:
            valid.append(model.model_validate(item))
        except ValidationError:
            continue
    return valid


def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _evidence_to_findings(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for item in evidence:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        findings.append({
            "claim": item.get("claim"),
            "source_title": source.get("title"),
            "source_url": source.get("url"),
            "support_status": item.get("support_status"),
            "supporting_excerpt": item.get("supporting_excerpt"),
            "validation_notes": item.get("validation_notes"),
        })
    return findings


def _evidence_to_sources(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    sources = []
    for item in evidence:
        source = item.get("source")
        if not isinstance(source, dict):
            continue
        key = (source.get("title"), source.get("url"))
        if key in seen or (not key[0] and not key[1]):
            continue
        seen.add(key)
        sources.append({
            "title": source.get("title"),
            "url": source.get("url"),
            "publication_date": source.get("publication_date"),
        })
    return sources


def _evidence_to_validation(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim": finding["claim"],
            "source_url": finding["source_url"],
            "url_accessible": None,
            "support_status": finding["support_status"],
            "supporting_excerpt": finding["supporting_excerpt"],
            "validation_notes": finding["validation_notes"],
        }
        for finding in _evidence_to_findings(evidence)
    ]


def normalize_workflow_response(raw: Any, question: str, request_id: str) -> ResearchResponse:
    """
    Convert the Make.com output into the public ResearchResponse.
    Accepts the target contract (executive_summary, key_findings, sources, solutions, ...)
    and the Decision Agent field names from make/prompts (summary, alternatives, evidence).
    Only content the workflow actually returned is kept. Nothing is invented.
    """
    if not isinstance(raw, dict):
        raise InvalidWorkflowResponseError()

    data = _clean(raw)

    status_value = data.get("status")
    if isinstance(status_value, str) and status_value.lower() in FAILURE_STATUSES:
        raise WorkflowFailedError()
    if not isinstance(status_value, str) or status_value not in SUCCESS_STATUSES:
        raise InvalidWorkflowResponseError("The workflow did not return a valid status.")

    body_src = data["report"] if isinstance(data.get("report"), dict) else data
    evidence = _dict_items(body_src.get("evidence"))

    key_findings = _valid_models(
        KeyFinding,
        _dict_items(body_src.get("key_findings")) or _evidence_to_findings(evidence),
    )
    sources = _valid_models(
        SourceRef,
        _dict_items(body_src.get("sources")) or _evidence_to_sources(evidence),
    )
    validation_results = _valid_models(
        ValidationResult,
        _dict_items(body_src.get("validation_results")) or _evidence_to_validation(evidence),
    )

    solution_items = _dict_items(_pick(body_src, "solutions", "alternatives"))
    for item in solution_items:
        item["supporting_study_titles"] = _str_items(item.get("supporting_study_titles"))
    solutions = _valid_models(Solution, solution_items)

    try:
        body = ReportBody(
            question=question,
            executive_summary=_opt_str(_pick(body_src, "executive_summary", "summary")),
            key_findings=key_findings,
            sources=sources,
            solutions=solutions,
            counterarguments=_str_items(body_src.get("counterarguments")),
            validation_results=validation_results,
            recommendation=_opt_str(body_src.get("recommendation")),
            uncertainty=_str_items(body_src.get("uncertainty")),
            limitations=_str_items(body_src.get("limitations")),
        )
    except ValidationError:
        raise InvalidWorkflowResponseError("The workflow response did not match the expected format.")

    return ResearchResponse(
        request_id=request_id,
        status=ResearchStatus(status_value),
        demo=False,
        report=body,
    )


def build_demo_response(question: str, request_id: str) -> ResearchResponse:
    """Clearly labeled placeholder output. It is never presented as research."""
    body = ReportBody(
        question=question,
        executive_summary="DEMO OUTPUT: illustrative placeholder for interface testing only. No research was performed.",
        recommendation=None,
        uncertainty=["Demo output is placeholder content and is not verified research."],
        limitations=["Demo mode does not query literature, check sources, or run agents."],
    )
    return ResearchResponse(
        request_id=request_id,
        status=ResearchStatus.DEMO,
        demo=True,
        report=body,
    )