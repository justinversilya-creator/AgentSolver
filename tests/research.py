import asyncio

import pytest

from backend.agents.research_agent import (
    ProviderError,
    ProviderNotConfiguredError,
    ResearchAgent,
    SearchRecord,
    build_query,
    split_subquestions,
)
from backend.schemas.evidence import RetrievalStatus

QUESTION = "Does spaced repetition improve long-term retention compared with massed practice?"


class FakeProvider:
    """Test double. Returns preset records and never performs network calls."""

    name = "fake"

    def __init__(self, records=None, error: Exception | None = None) -> None:
        self._records = records or []
        self._error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, max_results: int) -> list[SearchRecord]:
        self.calls.append((query, max_results))
        if self._error:
            raise self._error
        return self._records


def run(agent: ResearchAgent, question: str = QUESTION, request_id: str = "req-1"):
    return asyncio.run(agent.run(question, request_id))


def test_no_provider_raises_configuration_error():
    agent = ResearchAgent(provider=None)
    with pytest.raises(ProviderNotConfiguredError):
        run(agent)


def test_metadata_only_record_is_not_marked_as_inspected():
    provider = FakeProvider([
        SearchRecord(title="A study", url="https://doi.org/10.1000/xyz", publisher="Journal X"),
    ])

    result = run(ResearchAgent(provider))

    source = result.sources[0]
    assert source.source_id == "S1"
    assert source.retrieval_status is RetrievalStatus.METADATA_ONLY
    assert source.content_retrieved is False
    assert source.retrieved_excerpt is None
    assert source.metadata_returned is True
    assert result.key_findings == []
    assert any("not inspected" in gap for gap in result.evidence_gaps)


def test_retrieved_abstract_creates_traceable_finding():
    provider = FakeProvider([
        SearchRecord(
            title="Spacing and retention",
            url="https://example.org/paper",
            abstract="Spaced practice produced better delayed recall than massed practice.",
            content_retrieved=True,
        ),
    ])

    result = run(ResearchAgent(provider))

    assert result.sources[0].retrieval_status is RetrievalStatus.CONTENT_RETRIEVED
    assert result.sources[0].retrieved_excerpt.startswith("Spaced practice")
    assert len(result.key_findings) == 1
    assert result.key_findings[0].source_ids == ["S1"]
    assert "Abstract of S1 states:" in result.key_findings[0].claim


def test_failed_retrieval_is_reported_as_failed():
    provider = FakeProvider([
        SearchRecord(title="Broken", url="https://example.org/x", retrieval_failed=True),
    ])

    result = run(ResearchAgent(provider))

    assert result.sources[0].retrieval_status is RetrievalStatus.FAILED
    assert result.key_findings == []


def test_provider_error_returns_limitation_not_fake_sources():
    provider = FakeProvider(error=ProviderError("boom"))

    result = run(ResearchAgent(provider))

    assert result.sources == []
    assert result.key_findings == []
    assert any("search provider request failed" in lim for lim in result.research_limitations)
    assert "boom" not in " ".join(result.research_limitations)


def test_empty_results_report_evidence_gap():
    result = run(ResearchAgent(FakeProvider([])))

    assert result.sources == []
    assert any("returned no records" in gap for gap in result.evidence_gaps)


def test_invalid_url_is_dropped_not_kept():
    provider = FakeProvider([SearchRecord(title="Odd", url="javascript:alert(1)")])

    result = run(ResearchAgent(provider))

    assert result.sources[0].url is None
    assert any("No URL" in lim for lim in result.sources[0].limitations)


def test_max_results_is_passed_to_provider_and_capped():
    provider = FakeProvider([])
    run(ResearchAgent(provider, max_results=10_000))
    assert provider.calls[0][1] == 25


def test_query_and_subquestions_are_derived_deterministically():
    assert build_query("  Does   spaced repetition  help? ") == "Does spaced repetition help?"
    terms = split_subquestions(QUESTION)
    assert "spaced" in terms
    assert "repetition" in terms
    assert "the" not in terms