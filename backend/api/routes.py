"""
AgentSolve AI API routes (mounted under /api).

  GET  /api/health            Service status. Make.com reachability is not checked.
  POST /api/research          Validates the question, calls the Make.com webhook, returns a ResearchResponse.
  GET  /api/research/history  Persistence not implemented; returns an empty list.
"""
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from backend.api.health import router as health_router
from backend.config import get_settings
from backend.schemas.report import ResearchResponse
from backend.schemas.research import ResearchRequest, resolve_request_id
from backend.services import make_client, report_service
from backend.utils.errors import AppError, error_payload

REQUEST_ID_HEADER = "X-Request-ID"

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)

ERROR_RESPONSES = {
    400: {"description": "Invalid input"},
    422: {"description": "Validation error"},
    502: {"description": "Workflow error or invalid workflow response"},
    503: {"description": "Workflow not configured"},
    504: {"description": "Workflow timed out"},
}


@api_router.post("/research", response_model=ResearchResponse, responses=ERROR_RESPONSES)
async def create_research(payload: ResearchRequest, response: Response):
    request_id = resolve_request_id(payload.request_id)
    response.headers[REQUEST_ID_HEADER] = request_id
    settings = get_settings()

    try:
        if settings.demo_mode:
            return report_service.build_demo_response(payload.question, request_id)

        raw = await make_client.run_research(payload.question, request_id)
        return report_service.normalize_workflow_response(raw, payload.question, request_id)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, request_id),
            headers={REQUEST_ID_HEADER: request_id},
        )


@api_router.get("/research/history")
async def research_history() -> dict:
    return {
        "persistence": "not_implemented",
        "items": [],
    }