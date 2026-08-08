"""C3A Core API gateway.

This service is the only backend that the UI calls directly. It forwards AI
requests to c3a-core-ai over HTTP and keeps the existing UI-facing contract.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import date

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.ai_client import AiClient, AiServiceUnavailable
from app.db import DatabaseHealthChecker, close_database_pool, open_database_pool
from app.logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from app.repositories.visit_repository import (
    VisitNotFoundError,
    VisitRepository,
    VisitRepositoryUnavailable,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    CompleteVisitRequest,
    ScenarioResponse,
    ShiftSummaryResponse,
    StartVisitRequest,
    TaskIssueRequest,
    TaskStatusRequest,
    UpdatePatientProfileRequest,
    UploadRequest,
    UploadResponse,
    VisitQueueResponse,
)


load_dotenv()

LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG_BACKEND", "").lower() == "true" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="C3A Core API", version="1.0.0")
ai_client = AiClient()
database_health_checker = DatabaseHealthChecker()
visit_repository = VisitRepository()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
add_http_logging_middleware(
    app=app,
    logger=logger,
    debug_enabled=os.getenv("DEBUG_BACKEND", "").lower() == "true",
)
add_exception_handlers(
    app=app,
    logger=logger,
    debug_enabled=os.getenv("DEBUG_BACKEND", "").lower() == "true",
)


def _latest_user_query(req: ChatRequest) -> str:
    for message in reversed(req.messages):
        if message.role == "user":
            return message.content
    return ""


def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _reply_with_sources(reply: str, sources: list[str]) -> str:
    if not sources:
        return reply
    source_lines = "\n".join(f"{index}. {source}" for index, source in enumerate(sources, start=1))
    return f"{reply.rstrip()}\n\nSources:\n{source_lines}"


def _uses_database_context(ai_response) -> bool:
    database_context = (ai_response.rag or {}).get("database_context", {})
    return bool(database_context.get("used_for_chat"))


def _visit_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VisitRepositoryUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, VisitNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    logger.exception("Visit repository operation failed")
    return HTTPException(status_code=500, detail="Visit workflow database operation failed")


@app.on_event("startup")
async def startup_log_summary():
    open_database_pool()
    logger.info(
        "C3A Core API startup port=%s debug_backend=%s ai_base_url=%s ai_timeout_seconds=%s database_configured=%s",
        os.getenv("C3A_API_PORT", "8000"),
        os.getenv("DEBUG_BACKEND", "").lower() == "true",
        ai_client.base_url,
        ai_client.timeout,
        database_health_checker.configured,
    )


@app.on_event("shutdown")
async def shutdown_database_pool():
    close_database_pool()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "c3a-core-api",
        "ai": await ai_client.health(),
        "database": await database_health_checker.health(),
    }


@app.get("/workers/{worker_id}/visits", response_model=VisitQueueResponse)
def list_worker_visits(worker_id: str, date: date):
    try:
        return VisitQueueResponse(visits=visit_repository.list_visit_queue(worker_id, date))
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.get("/workers/{worker_id}/shift-summary", response_model=ShiftSummaryResponse)
def worker_shift_summary(worker_id: str, date: date):
    try:
        return ShiftSummaryResponse(**visit_repository.shift_summary(worker_id, date))
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.get("/visits/{visit_id}", response_model=ScenarioResponse)
def get_visit(visit_id: str):
    try:
        return ScenarioResponse.model_validate(visit_repository.get_scenario(visit_id))
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.patch("/patients/{patient_id}/profile", response_model=ScenarioResponse)
def update_patient_profile(patient_id: str, req: UpdatePatientProfileRequest):
    try:
        payload = req.model_dump(exclude_unset=True)
        if req.name is not None:
            payload["displayName"] = req.name
        return ScenarioResponse.model_validate(
            visit_repository.update_patient_profile(patient_id, payload)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/start", response_model=ScenarioResponse)
def start_visit(visit_id: str, req: StartVisitRequest):
    try:
        snapshot = req.checkIn.model_dump(exclude_none=True) if req.checkIn else None
        return ScenarioResponse.model_validate(
            visit_repository.start_visit(visit_id, req.workerId, snapshot)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/tasks/{task_id}/complete", response_model=ScenarioResponse)
def complete_task(visit_id: str, task_id: str, req: TaskStatusRequest | None = None):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.complete_task(visit_id, task_id, req.workerId if req else None)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.patch("/visits/{visit_id}/tasks/{task_id}", response_model=ScenarioResponse)
def update_task(visit_id: str, task_id: str, req: TaskStatusRequest):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.update_task_status(visit_id, task_id, req.status, req.workerId)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/tasks/{task_id}/issue", response_model=ScenarioResponse)
def report_task_issue(visit_id: str, task_id: str, req: TaskIssueRequest):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.report_task_issue(visit_id, task_id, req.type, req.workerId)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/complete", response_model=ScenarioResponse)
def complete_visit(visit_id: str, req: CompleteVisitRequest):
    try:
        snapshot = req.checkOut.model_dump(exclude_none=True) if req.checkOut else None
        return ScenarioResponse.model_validate(
            visit_repository.complete_visit(visit_id, req.workerId, snapshot)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    started_at = time.perf_counter()
    logger.info(
        "API POST /chat received messages=%s attachments=%s latest_user_preview=%r",
        len(req.messages),
        len(req.attachments or []),
        _preview(_latest_user_query(req)),
    )
    logger.debug("API POST /chat payload=%s", preview_object(req.model_dump(exclude_none=True)))
    try:
        ai_response = await ai_client.chat(
            req,
            request_id=getattr(request.state, "request_id", None),
        )
        logger.info(
            "API POST /chat completed total_elapsed_ms=%.1f reply_chars=%s sources=%s",
            (time.perf_counter() - started_at) * 1000,
            len(ai_response.reply),
            len(ai_response.sources),
        )
        logger.debug(
            "API POST /chat ai_response=%s",
            preview_object(ai_response.model_dump()),
        )
        if _uses_database_context(ai_response):
            return ChatResponse(reply=ai_response.reply)
        return ChatResponse(reply=_reply_with_sources(ai_response.reply, ai_response.sources))
    except AiServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    request_id = getattr(request.state, "request_id", None)

    async def forward_stream():
        try:
            async for chunk in ai_client.stream_chat(req, request_id=request_id):
                yield chunk
        except AiServiceUnavailable:
            yield (json.dumps({"type": "error", "message": "AI service is unavailable"}) + "\n").encode()

    return StreamingResponse(
        forward_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/upload", response_model=UploadResponse)
async def upload(req: UploadRequest):
    try:
        logger.info(
            "API POST /upload received filename=%s mime_type=%s base64_chars=%s",
            req.filename,
            req.mimeType,
            len(req.base64),
        )
        file_id = str(uuid.uuid4())
        ext = req.mimeType.split("/")[-1]
        path = f"/tmp/{file_id}.{ext}"
        data = base64.b64decode(req.base64)
        with open(path, "wb") as handle:
            handle.write(data)
        logger.info("API POST /upload saved path=%s bytes=%s", path, len(data))
        return UploadResponse(fileId=file_id, url=f"/files/{file_id}.{ext}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("C3A_API_PORT", "8000")),
        reload=True,
    )
