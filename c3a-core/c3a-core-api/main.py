"""C3A Core API gateway.

This service is the only backend that the UI calls directly. It forwards AI
requests to c3a-core-ai over HTTP and keeps the existing UI-facing contract.
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai_client import AiClient, AiServiceUnavailable
from app.db import DatabaseHealthChecker
from app.logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from app.schemas import ChatRequest, ChatResponse, UploadRequest, UploadResponse


load_dotenv()

LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG_BACKEND", "").lower() == "true" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="C3A Core API", version="1.0.0")
ai_client = AiClient()
database_health_checker = DatabaseHealthChecker()

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


@app.on_event("startup")
async def startup_log_summary():
    logger.info(
        "C3A Core API startup port=%s debug_backend=%s ai_base_url=%s ai_timeout_seconds=%s database_configured=%s",
        os.getenv("C3A_API_PORT", "8000"),
        os.getenv("DEBUG_BACKEND", "").lower() == "true",
        ai_client.base_url,
        ai_client.timeout,
        database_health_checker.configured,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "c3a-core-api",
        "ai": await ai_client.health(),
        "database": await database_health_checker.health(),
    }


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
