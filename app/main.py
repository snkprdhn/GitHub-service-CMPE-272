"""HTTP entry point for the GitHub Issues Service."""

# Author: Sonit — application setup, health check, request IDs, and error responses.

import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.github import GitHubAPIError
from app.issues import router as issues_router
from app.models import ErrorResponse
from app.webhook_routes import router as webhook_router
from app.webhooks import WebhookError

logger = logging.getLogger("github_issues_service.requests")
app = FastAPI(
    title="GitHub Issues Service",
    version="1.0.0",
    description="A small API wrapper around GitHub Issues for one repository.",
)
app.include_router(issues_router)
app.include_router(webhook_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        json.dumps(
            {
                "message": "request_complete",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            }
        )
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(error["msg"] for error in exc.errors())
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(detail=detail, status=400, request_id=request.state.request_id).model_dump(),
    )


@app.exception_handler(GitHubAPIError)
async def github_error_handler(request: Request, exc: GitHubAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            detail=exc.detail,
            status=exc.status_code,
            request_id=request.state.request_id,
        ).model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(WebhookError)
async def webhook_error_handler(request: Request, exc: WebhookError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            detail=exc.detail,
            status=exc.status_code,
            request_id=request.state.request_id,
        ).model_dump(),
    )


@app.get("/healthz", tags=["service"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
