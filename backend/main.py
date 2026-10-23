# backend/main.py
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.routes import api_router
from backend.config import APP_VERSION, get_settings
from backend.utils.errors import AppError, error_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agentsolve")

settings = get_settings()

app = FastAPI(
    title="AgentSolve AI API",
    version=APP_VERSION,
    description="Evidence-first multi-agent research API. Agent orchestration runs in n8n.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"]
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
            "message": str(err.get("msg", "Invalid value.")),
        }
        for err in exc.errors()
    ]
    payload = error_payload("invalid_input", "The request input is invalid.")
    payload["error"]["details"] = details
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be processed."
    return JSONResponse(status_code=exc.status_code, content=error_payload("http_error", message))


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content=error_payload("internal_error", "An unexpected error occurred. Please try again later."),
    )


app.include_router(api_router)


@app.get("/", tags=["root"])
async def root() -> dict:
    return {
        "name": "AgentSolve AI API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }