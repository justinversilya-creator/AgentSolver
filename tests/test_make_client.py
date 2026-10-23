import asyncio
import json

import httpx
import pytest

from backend.config import get_settings
from backend.services import make_client
from backend.utils.errors import (
    InvalidWorkflowResponseError,
    ServiceNotConfiguredError,
    WorkflowConnectionError,
    WorkflowHTTPError,
    WorkflowTimeoutError,
)

WEBHOOK = "https://hook.example.com/test-webhook"
QUESTION = "Does spaced repetition improve retention?"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("MAKE_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("MAKE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "5")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run(handler, request_id="req-123"):
    transport = httpx.MockTransport(handler)
    return asyncio.run(make_client.run_research(QUESTION, request_id, transport=transport))


def test_success_sends_contract_and_returns_object(configured):
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        captured["token"] = request.headers.get("X-AgentSolve-Token")
        captured["request_id"] = request.headers.get("X-Request-ID")
        return httpx.Response(200, json={"status": "completed", "summary": "Text."})

    result = run(handler)

    assert result == {"status": "completed", "summary": "Text."}
    assert captured["payload"] == {
        "contract_version": "1.0",
        "request_id": "req-123",
        "question": QUESTION,
    }
    assert captured["token"] == "test-secret"
    assert captured["request_id"] == "req-123"


def test_single_item_array_is_unwrapped(configured):
    result = run(lambda request: httpx.Response(200, json=[{"status": "completed"}]))
    assert result == {"status": "completed"}


def test_multi_item_array_is_rejected(configured):
    with pytest.raises(InvalidWorkflowResponseError):
        run(lambda request: httpx.Response(200, json=[{"status": "a"}, {"status": "b"}]))


def test_non_2xx_raises_http_error(configured):
    with pytest.raises(WorkflowHTTPError):
        run(lambda request: httpx.Response(500, text="internal detail"))


def test_non_json_response_is_rejected(configured):
    with pytest.raises(InvalidWorkflowResponseError):
        run(lambda request: httpx.Response(200, text="Accepted"))


def test_timeout_maps_to_workflow_timeout(configured):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(WorkflowTimeoutError):
        run(handler)


def test_connection_failure_maps_to_connection_error(configured):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(WorkflowConnectionError):
        run(handler)


def test_missing_configuration_raises_before_any_request(monkeypatch):
    monkeypatch.setenv("MAKE_WEBHOOK_URL", "")
    get_settings.cache_clear()

    def handler(request):
        raise AssertionError("No request should be sent when unconfigured.")

    with pytest.raises(ServiceNotConfiguredError):
        run(handler)
    get_settings.cache_clear()