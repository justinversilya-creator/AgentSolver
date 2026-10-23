import logging
from typing import Any

import httpx

from backend.config import get_settings
from backend.utils.errors import (
    InvalidWorkflowResponseError,
    ServiceNotConfiguredError,
    WorkflowConnectionError,
    WorkflowHTTPError,
    WorkflowTimeoutError,
)

logger = logging.getLogger("agentsolve.make")

# Optional shared secret. Make.com custom webhooks have no built-in header auth,
# so add a Filter after the webhook that checks this header equals your secret.
AUTH_HEADER = "X-AgentSolve-Token"
REQUEST_ID_HEADER = "X-Request-ID"
CONTRACT_VERSION = "1.0"
MAX_RESPONSE_BYTES = 1_000_000


def _build_timeout(read_timeout: float) -> httpx.Timeout:
    return httpx.Timeout(connect=5.0, read=read_timeout, write=10.0, pool=5.0)


def _unwrap(data: Any) -> dict[str, Any]:
    """Accept a JSON object, or an array containing exactly one object."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    raise InvalidWorkflowResponseError("The workflow returned an unsupported response format.")


async def run_research(
    question: str,
    request_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """
    Send the validated question to the Make.com custom webhook and return the decoded JSON object.
    POST requests are never retried automatically, to avoid duplicate scenario runs.
    The optional transport parameter exists for tests only.
    """
    settings = get_settings()
    url = settings.make_webhook_url

    if not settings.make_configured or not url:
        raise ServiceNotConfiguredError()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        REQUEST_ID_HEADER: request_id,
    }
    if settings.make_webhook_secret:
        headers[AUTH_HEADER] = settings.make_webhook_secret

    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "question": question,
    }

    try:
        async with httpx.AsyncClient(
            timeout=_build_timeout(settings.request_timeout_seconds),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        logger.warning("Make.com webhook timed out (request_id=%s)", request_id)
        raise WorkflowTimeoutError()
    except httpx.HTTPError as exc:
        logger.warning("Make.com webhook unreachable (request_id=%s): %s", request_id, type(exc).__name__)
        raise WorkflowConnectionError()

    if not 200 <= response.status_code < 300:
        logger.warning("Make.com webhook returned HTTP %s (request_id=%s)", response.status_code, request_id)
        raise WorkflowHTTPError(response.status_code)

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise InvalidWorkflowResponseError("The workflow response is too large.")

    try:
        data = response.json()
    except ValueError:
        raise InvalidWorkflowResponseError("The workflow returned a non-JSON response.")

    return _unwrap(data)