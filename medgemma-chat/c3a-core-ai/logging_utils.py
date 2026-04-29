"""Shared logging helpers for the AI service."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from starlette.responses import Response


REDACTED_KEYS = {"authorization", "api_key", "apikey", "base64"}


def add_http_logging_middleware(app: FastAPI, logger: logging.Logger, debug_enabled: bool) -> None:
    @app.middleware("http")
    async def http_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        request.state.started_at = started_at

        body_bytes = await request.body()
        request._receive = _receive_with_cached_body(body_bytes)  # type: ignore[attr-defined]
        body_preview = preview_json_bytes(body_bytes)
        request.state.body_preview = body_preview
        logger.info(
            "HTTP request started request_id=%s method=%s path=%s client=%s query=%r",
            request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
            str(request.url.query),
        )
        if debug_enabled and body_preview:
            logger.debug(
                "HTTP request body request_id=%s body=%s",
                request_id,
                body_preview,
            )

        response = await call_next(request)

        response_body = await _collect_response_body(response)
        response_preview = preview_json_bytes(response_body)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "HTTP request completed request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        if debug_enabled and response_preview:
            logger.debug(
                "HTTP response body request_id=%s body=%s",
                request_id,
                response_preview,
            )

        cloned = clone_response(response, response_body)
        cloned.headers["x-request-id"] = request_id
        return cloned


def add_exception_handlers(app: FastAPI, logger: logging.Logger, debug_enabled: bool) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            "HTTP validation failed request_id=%s method=%s path=%s errors=%s body=%s",
            request_id,
            request.method,
            request.url.path,
            exc.errors(),
            getattr(request.state, "body_preview", ""),
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": exc.errors(),
                "requestId": request_id,
            },
            headers={"x-request-id": request_id},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", "unknown")
        log_fn = logger.error if exc.status_code >= 500 else logger.warning
        log_fn(
            "HTTP exception request_id=%s method=%s path=%s status=%s detail=%r body=%s",
            request_id,
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
            getattr(request.state, "body_preview", ""),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "requestId": request_id},
            headers={"x-request-id": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(
            "Unhandled exception request_id=%s method=%s path=%s body=%s",
            request_id,
            request.method,
            request.url.path,
            getattr(request.state, "body_preview", ""),
        )
        detail = str(exc) if debug_enabled else "Internal server error"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "requestId": request_id},
            headers={"x-request-id": request_id},
        )


def preview_json_bytes(body: bytes, limit: int = 800) -> str:
    if not body:
        return ""
    try:
        decoded = json.loads(body.decode("utf-8"))
        return preview_object(decoded, limit=limit)
    except Exception:
        text = body.decode("utf-8", errors="replace")
        return _trim(text, limit)


def preview_object(value: Any, limit: int = 800) -> str:
    sanitized = _sanitize(value)
    text = json.dumps(sanitized, ensure_ascii=True)
    return _trim(text, limit)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if key.lower() in REDACTED_KEYS else _sanitize(inner))
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _trim(" ".join(value.split()), 240)
    return value


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _receive_with_cached_body(body: bytes):
    done = False

    async def receive():
        nonlocal done
        if done:
            return {"type": "http.request", "body": b"", "more_body": False}
        done = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _collect_response_body(response: Response) -> bytes:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    return body


def clone_response(response: Response, body: bytes) -> Response:
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )
