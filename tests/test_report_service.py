import pytest

from backend.schemas.report import ResearchStatus
from backend.services import report_service
from backend.utils.errors import InvalidWorkflowResponseError, WorkflowFailedError

QUESTION = "Does spaced repetition improve retention?"


def test_completed_response_is_normalized():
    raw = {
        "status": "completed",
        "summary": "Summary text.",
        "recommendation": "Use spacing.",
        "alternatives": [
            {"title": "Spaced repetition", "description": "Desc.", "supporting_study_titles": ["Study A"]}
        ],
        "evidence": [
            {
                "claim": "Spacing improves recall.",
                "source": {"title": "Study A", "url": "https://doi.org/10.1000/abc"},
                "support_status": "verified",
                "supporting_excerpt": "Excerpt.",
                "validation_notes": "Checked.",
            }
        ],
        "counterarguments": ["Small samples."],
        "limitations": ["Single domain."],
    }

    result = report_service.normalize_workflow_response(raw, QUESTION, "req-1")

    assert result.request_id == "req-1"
    assert result.status == ResearchStatus.COMPLETED
    assert result.demo is False
    assert result.report.executive_summary == "Summary text."
    assert result.report.solutions[0].title == "Spaced repetition"
    assert result.report.key_findings[0].support_status.value == "verified"
    assert result.report.sources[0].url == "https://doi.org/10.1000/abc"
    assert result.report.validation_results[0].claim == "Spacing improves recall."


def test_invalid_url_is_dropped_and_unknown_status_is_not_upgraded():
    raw = {
        "status": "completed",
        "evidence": [
            {
                "claim": "Claim.",
                "source": {"title": "T", "url": "javascript:alert(1)"},
                "support_status": "definitely_true",
            }
        ],
    }

    result = report_service.normalize_workflow_response(raw, QUESTION, "req-2")

    assert result.report.sources[0].url is None
    assert result.report.key_findings[0].source_url is None
    assert result.report.key_findings[0].support_status.value == "unverified"


def test_no_evidence_means_no_invented_sources():
    result = report_service.normalize_workflow_response(
        {"status": "insufficient_evidence"}, QUESTION, "req-3"
    )
    assert result.status == ResearchStatus.INSUFFICIENT_EVIDENCE
    assert result.report.sources == []
    assert result.report.key_findings == []
    assert result.report.validation_results == []


def test_items_without_claim_are_dropped():
    raw = {
        "status": "partial",
        "key_findings": [
            {"support_status": "verified"},
            {"claim": "Real claim.", "support_status": "partially_supported"},
        ],
    }

    result = report_service.normalize_workflow_response(raw, QUESTION, "req-4")

    assert len(result.report.key_findings) == 1
    assert result.report.key_findings[0].claim == "Real claim."


def test_failed_status_raises_workflow_failed():
    with pytest.raises(WorkflowFailedError):
        report_service.normalize_workflow_response({"status": "failed"}, QUESTION, "req-5")


def test_unknown_status_is_rejected():
    with pytest.raises(InvalidWorkflowResponseError):
        report_service.normalize_workflow_response({"status": "maybe"}, QUESTION, "req-6")


def test_non_dict_response_is_rejected():
    with pytest.raises(InvalidWorkflowResponseError):
        report_service.normalize_workflow_response(["not", "a", "dict"], QUESTION, "req-7")


def test_demo_response_is_clearly_labeled():
    result = report_service.build_demo_response(QUESTION, "req-8")

    assert result.demo is True
    assert result.status == ResearchStatus.DEMO
    assert result.report.key_findings == []
    assert result.report.sources == []
    assert "DEMO OUTPUT" in result.report.executive_summary