from typing import Any


class AppError(Exception):
    """Base application error with a safe, client-facing message."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidInputError(AppError):
    status_code = 400
    code = "invalid_input"
    default_message = "The request input is invalid."


class ServiceNotConfiguredError(AppError):
    status_code = 503
    code = "service_not_configured"
    default_message = "The research workflow is not configured yet. Set MAKE_WEBHOOK_URL on the server."


class WorkflowConnectionError(AppError):
    status_code = 502
    code = "workflow_unreachable"
    default_message = "The research workflow could not be reached."


class WorkflowTimeoutError(AppError):
    status_code = 504
    code = "workflow_timeout"
    default_message = "The research workflow did not respond in time."


class WorkflowHTTPError(AppError):
    status_code = 502
    code = "workflow_error"
    default_message = "The research workflow returned an error."

    def __init__(self, upstream_status: int | None = None, message: str | None = None) -> None:
        self.upstream_status = upstream_status
        super().__init__(message)


class WorkflowFailedError(AppError):
    status_code = 502
    code = "workflow_failed"
    default_message = "The research workflow could not complete this request."


class InvalidWorkflowResponseError(AppError):
    status_code = 502
    code = "invalid_workflow_response"
    default_message = "The research workflow returned an unexpected response."


def error_payload(code: str, message: str, request_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id:
        body["request_id"] = request_id
    return body