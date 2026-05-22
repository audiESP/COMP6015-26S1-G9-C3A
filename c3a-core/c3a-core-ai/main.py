"""C3A Core AI service.

This service owns MedGemma inference, Qdrant retrieval, and RAG citation data.
The API gateway calls this service over HTTP.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chat_router import RouteDecision, decide_route, with_effective_mode
from db_context import DbContextResult, DbContextRetriever
from logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from medgemma_service import MedGemmaService
from rag.citations import RetrievedChunk
from rag.retriever import RagRetriever


SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env", override=False)
load_dotenv(override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


LOG_LEVEL = logging.DEBUG if os.getenv(
    "DEBUG_BACKEND", "").lower() == "true" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)
AI_ENABLED = _env_bool("C3A_AI_ENABLED", True)
CHAT_RAG_ENABLED = _env_bool("CHAT_RAG_ENABLED", True)
CHAT_RAG_TOP_K = int(os.getenv("CHAT_RAG_TOP_K", os.getenv("RAG_TOP_K", "5")))
CHAT_RAG_MAX_CHARS_PER_CHUNK = int(os.getenv("CHAT_RAG_MAX_CHARS_PER_CHUNK", "900"))
CHAT_RAG_MIN_SCORE = float(os.getenv("CHAT_RAG_MIN_SCORE", "0.0"))

app = FastAPI(title="C3A Core AI", version="1.0.0")

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

service = MedGemmaService(enabled=AI_ENABLED)
rag_retriever = RagRetriever()
db_context_retriever = DbContextRetriever()


class ChatMessage(BaseModel):
    role: str
    content: str


class PatientContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    medicalRecordNumber: Optional[str] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    preferredLanguage: Optional[str] = None
    interpreterRequired: Optional[bool] = None
    culturalBackground: Optional[str] = None
    mobilitySupport: Optional[str] = None
    cognitiveStatus: Optional[str] = None
    dietaryNotes: Optional[str] = None
    communicationNotes: Optional[str] = None
    careRiskFlags: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    medications: Optional[list[str]] = None


class WorkerContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    shift: Optional[str] = None


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class LocationSnapshot(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    coords: Optional[GeoPoint] = None
    accuracyMeters: Optional[float] = None
    distanceFromPlannedMeters: Optional[float] = None
    withinExpectedArea: Optional[bool] = None
    permissionStatus: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


class VisitContext(BaseModel):
    id: Optional[str] = None
    patientId: Optional[str] = None
    scheduledAt: Optional[str] = None
    arrivedAt: Optional[str] = None
    location: Optional[str] = None
    plannedAddress: Optional[str] = None
    plannedCoords: Optional[GeoPoint] = None
    locationThresholdMeters: Optional[float] = None
    checkIn: Optional[LocationSnapshot] = None
    checkOut: Optional[LocationSnapshot] = None
    status: Optional[str] = None


class CareTaskContext(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    dueAt: Optional[str] = None
    detail: Optional[str] = None


class ScenarioEventContext(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    note: Optional[str] = None


class RiskContext(BaseModel):
    id: Optional[str] = None
    level: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None


class AttachmentData(BaseModel):
    type: str
    base64: str
    mimeType: str


class AiChatRequest(BaseModel):
    messages: list[ChatMessage]
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    attachments: Optional[list[AttachmentData]] = None


class AiChatResponse(BaseModel):
    reply: str
    sources: list[str] = []
    rag: dict[str, Any] = {}
    model: dict[str, Any] = {}


class RagSearchRequest(BaseModel):
    query: str
    topK: Optional[int] = None


@app.on_event("startup")
async def startup_log_summary():
    logger.info(
        "C3A Core AI startup port=%s debug_backend=%s ai_enabled=%s model=%s device=%s rag=%s",
        os.getenv("C3A_AI_PORT", "8001"),
        os.getenv("DEBUG_BACKEND", "").lower() == "true",
        AI_ENABLED,
        service.status().get("model"),
        service.status().get("device"),
        preview_object(rag_retriever.status()),
    )


def _latest_user_query(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _query_preview(text: str, query: str, limit: int = 500) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact

    terms = _preview_terms(query)
    if not terms:
        return _preview(compact, limit)

    lowered = compact.lower()
    positions = [lowered.find(term)
                 for term in terms if lowered.find(term) >= 0]
    if not positions:
        return _preview(compact, limit)

    start = max(0, min(positions) - 70)
    end = min(len(compact), start + limit)
    if end - start < limit:
        start = max(0, end - limit)

    excerpt = compact[start:end].strip()
    if start > 0:
        excerpt = f"...{excerpt}"
    if end < len(compact):
        excerpt = f"{excerpt}..."
    return excerpt


def _preview_terms(query: str) -> list[str]:
    terms = [
        term
        for term in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", query.lower())
        if term
        not in {
            "about",
            "after",
            "aged",
            "care",
            "common",
            "does",
            "from",
            "have",
            "older",
            "patient",
            "patients",
            "person",
            "provider",
            "providers",
            "resident",
            "should",
            "their",
            "what",
            "when",
            "with",
            "worker",
        }
    ]
    if {"signs", "symptoms"} & set(terms):
        terms.extend(
            [
                "confused",
                "forgetful",
                "attention",
                "agitated",
                "withdrawn",
                "hallucinations",
            ]
        )
    return terms


def _rag_payload(chunks, query: str = "") -> dict[str, Any]:
    return {
        "results": [
            {
                "source_title": chunk.source_title,
                "source_filename": chunk.source_filename,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_heading": chunk.section_heading,
                "score": chunk.score,
                "doc_type": chunk.doc_type,
                "text_preview": _query_preview(chunk.text, query),
            }
            for chunk in chunks
        ]
    }


@app.get("/ai/health")
async def health():
    return {
        "status": "ok",
        "service": "c3a-core-ai",
        "model": service.status(),
        "rag": rag_retriever.status(),
        "database_context": db_context_retriever.status(),
        "debug": {
            "debug_backend": os.getenv("DEBUG_BACKEND", "").lower() == "true",
            "ai_enabled": AI_ENABLED,
            "chat_uses_rag": CHAT_RAG_ENABLED,
        },
    }


@app.post("/ai/chat", response_model=AiChatResponse)
async def chat(req: AiChatRequest):
    started_at = time.perf_counter()
    latest_user_query = _latest_user_query(req.messages)
    initial_route = decide_route(latest_user_query, req.patientContext, req.attachments)
    logger.info(
        "AI POST /ai/chat received messages=%s attachments=%s patient_context=%s route=%s route_confidence=%.2f latest_user_preview=%r",
        len(req.messages),
        len(req.attachments or []),
        bool(req.patientContext),
        initial_route.mode,
        initial_route.confidence,
        _preview(latest_user_query),
    )
    logger.debug("AI POST /ai/chat payload=%s",
                 preview_object(req.model_dump(exclude_none=True)))

    rag_started_at = time.perf_counter()
    rag_chunks: list[RetrievedChunk] = []
    should_use_rag = initial_route.uses_rag
    if should_use_rag and CHAT_RAG_ENABLED and latest_user_query.strip() and rag_retriever.is_configured:
        rag_chunks = await _retrieve_for_chat(latest_user_query)
    else:
        logger.info(
            "AI POST /ai/chat RAG skipped route_uses_rag=%s enabled=%s configured=%s query_present=%s",
            should_use_rag,
            CHAT_RAG_ENABLED,
            rag_retriever.is_configured,
            bool(latest_user_query.strip()),
        )
    rag_elapsed_ms = (time.perf_counter() - rag_started_at) * 1000
    accepted_rag_chunks = _filter_rag_chunks(rag_chunks)
    rag_context = _build_chat_rag_context(accepted_rag_chunks)

    db_context_started_at = time.perf_counter()
    should_use_db = initial_route.uses_db
    if should_use_db:
        db_context_result = await db_context_retriever.retrieve(
            latest_user_query,
            patient_context=req.patientContext,
        )
    else:
        logger.info("AI POST /ai/chat PostgreSQL context skipped route_uses_db=%s", should_use_db)
        db_context_result = _empty_db_context_result()
    db_context_elapsed_ms = (time.perf_counter() - db_context_started_at) * 1000
    db_has_quality = _db_context_has_quality(db_context_result.metadata)
    rag_has_quality = bool(accepted_rag_chunks)
    effective_route, ambiguity_resolved_by = _resolve_effective_route(
        initial_route,
        db_has_quality=db_has_quality,
        rag_has_quality=rag_has_quality,
    )
    combined_context = _context_for_route(
        effective_route,
        db_context_result.context if db_has_quality else "",
        rag_context if rag_has_quality else "",
        ambiguous_initial=initial_route.mode == "uncertain",
    )

    generation_started_at = time.perf_counter()
    reply = await service.generate_reply(
        messages=[(message.role, message.content) for message in req.messages],
        patient=req.patientContext,
        worker=req.workerContext,
        visit=req.visitContext,
        tasks=req.taskContext or [],
        events=req.eventContext or [],
        risks=req.riskContext or [],
        attachments=req.attachments or [],
        rag_context=combined_context,
    )
    logger.info(
        "AI POST /ai/chat completed initial_route=%s effective_route=%s ambiguity_resolved_by=%s rag_retrieved=%s rag_accepted=%s rag_elapsed_ms=%.1f db_context_used=%s db_context_elapsed_ms=%.1f db_result_counts=%s generation_elapsed_ms=%.1f total_elapsed_ms=%.1f reply_chars=%s",
        initial_route.mode,
        effective_route.mode,
        ambiguity_resolved_by,
        len(rag_chunks),
        len(accepted_rag_chunks),
        rag_elapsed_ms,
        db_context_result.metadata.get("used_for_chat"),
        db_context_elapsed_ms,
        db_context_result.metadata.get("result_counts", {}),
        (time.perf_counter() - generation_started_at) * 1000,
        (time.perf_counter() - started_at) * 1000,
        len(reply),
    )
    rag_payload = _rag_payload(accepted_rag_chunks, latest_user_query)
    rag_payload.update(
        {
            "enabled_for_chat": CHAT_RAG_ENABLED,
            "used_for_chat": rag_has_quality,
            "top_k": CHAT_RAG_TOP_K,
            "status": rag_retriever.status(),
            "database_context": db_context_result.metadata,
            "rag_context": {
                "retrieved_count": len(rag_chunks),
                "accepted_count": len(accepted_rag_chunks),
                "min_score": CHAT_RAG_MIN_SCORE,
            },
            "route": {
                "initial_mode": initial_route.mode,
                "effective_mode": effective_route.mode,
                "uses_db": effective_route.uses_db,
                "uses_rag": effective_route.uses_rag,
                "confidence": initial_route.confidence,
                "reason": initial_route.reason,
                "matched_signals": initial_route.matched_signals,
                "ambiguity_resolved_by": ambiguity_resolved_by,
            },
        }
    )
    response = AiChatResponse(
        reply=reply,
        sources=_source_labels(accepted_rag_chunks),
        rag=rag_payload,
        model=service.status(),
    )
    logger.debug("AI POST /ai/chat response=%s",
                 preview_object(response.model_dump()))
    return response


@app.post("/ai/rag/search")
async def rag_search(req: RagSearchRequest):
    logger.info(
        "AI POST /ai/rag/search received query_preview=%r topK=%s",
        _preview(req.query),
        req.topK,
    )
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")
    if not rag_retriever.is_configured:
        logger.warning(
            "AI POST /ai/rag/search skipped because RAG is not configured status=%s",
            preview_object(rag_retriever.status()),
        )
        return {"results": [], "status": rag_retriever.status()}

    if req.topK is not None:
        results = rag_retriever.store.search(req.query, req.topK)
    else:
        results = await rag_retriever.retrieve(req.query)
    payload = _rag_payload(results, req.query)
    payload["status"] = rag_retriever.status()
    logger.info(
        "AI POST /ai/rag/search completed results=%s",
        len(payload["results"]),
    )
    logger.debug("AI POST /ai/rag/search response=%s", preview_object(payload))
    return payload


async def _retrieve_for_chat(query: str) -> list[RetrievedChunk]:
    if CHAT_RAG_TOP_K == rag_retriever.settings.top_k:
        return await rag_retriever.retrieve(query)

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None,
            rag_retriever.store.search,
            query,
            CHAT_RAG_TOP_K,
        )
    except Exception as exc:
        logger.warning("AI POST /ai/chat RAG retrieval failed: %s", exc, exc_info=True)
        return []


def _filter_rag_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if CHAT_RAG_MIN_SCORE <= 0:
        return chunks
    return [chunk for chunk in chunks if chunk.score >= CHAT_RAG_MIN_SCORE]


def _empty_db_context_result() -> DbContextResult:
    return DbContextResult(
        context="",
        metadata={
            "enabled_for_chat": db_context_retriever.enabled,
            "used_for_chat": False,
            "configured": db_context_retriever.configured,
            "matched_intents": [],
            "tables": [],
            "result_counts": {},
            "status": db_context_retriever.status(),
        },
    )


def _db_context_has_quality(metadata: dict[str, Any]) -> bool:
    if not metadata.get("used_for_chat"):
        return False
    result_counts = metadata.get("result_counts") or {}
    if not isinstance(result_counts, dict):
        return True
    return any(isinstance(count, int) and count > 0 for count in result_counts.values())


def _resolve_effective_route(
    initial_route: RouteDecision,
    *,
    db_has_quality: bool,
    rag_has_quality: bool,
) -> tuple[RouteDecision, str]:
    if initial_route.mode != "uncertain":
        return initial_route, "not_ambiguous"
    if db_has_quality and rag_has_quality:
        return (
            with_effective_mode(
                initial_route,
                "hybrid",
                "Ambiguous query had reliable database and RAG context.",
            ),
            "both_quality",
        )
    if db_has_quality:
        return (
            with_effective_mode(
                initial_route,
                "database_only",
                "Ambiguous query resolved to database context by retrieval quality.",
            ),
            "db_quality",
        )
    if rag_has_quality:
        return (
            with_effective_mode(
                initial_route,
                "rag_only",
                "Ambiguous query resolved to RAG context by retrieval quality.",
            ),
            "rag_quality",
        )
    return (
        with_effective_mode(
            initial_route,
            "direct_ai",
            "Ambiguous query had no reliable database or RAG context.",
        ),
        "no_quality",
    )


def _context_for_route(
    route: RouteDecision,
    db_context: str,
    rag_context: str,
    *,
    ambiguous_initial: bool,
) -> str:
    if route.mode == "database_only":
        return db_context or _missing_context_instruction("database")
    if route.mode == "rag_only":
        return rag_context or _missing_context_instruction("rag")
    if route.mode == "hybrid":
        return _combine_contexts(
            _hybrid_context_instruction(ambiguous_initial),
            db_context or _missing_context_instruction("database"),
            rag_context or _missing_context_instruction("rag"),
        )
    return ""


def _hybrid_context_instruction(ambiguous_initial: bool) -> str:
    parts = [
        "## Retrieval Source Boundaries",
        "PostgreSQL rows are synthetic patient facts.",
        "RAG evidence is care guideline/pathway evidence.",
        "Do not infer missing patient facts from RAG evidence.",
        "Do not cite patient database rows as guideline evidence.",
    ]
    if ambiguous_initial:
        parts.append(
            "The user's source intent was ambiguous; separate patient data found from guideline evidence found."
        )
    return "\n".join(parts)


def _missing_context_instruction(source: str) -> str:
    if source == "database":
        return (
            "## Missing PostgreSQL Synthetic Patient Context\n"
            "No reliable synthetic patient database rows were retrieved for this question. "
            "Do not invent patient-specific facts. If helpful, provide general clinical or care-work context and clearly state that no matching synthetic patient record was found."
        )
    return (
        "## Missing Clinical Evidence\n"
        "No reliable project RAG evidence was retrieved for this question. "
        "Do not cite project sources. If helpful, provide general clinical or care-work context and clearly state that no matching project guideline evidence was found."
    )


def _build_chat_rag_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""

    evidence_blocks = []
    for index, chunk in enumerate(chunks, start=1):
        text = " ".join(chunk.text.split())
        if len(text) > CHAT_RAG_MAX_CHARS_PER_CHUNK:
            text = f"{text[:CHAT_RAG_MAX_CHARS_PER_CHUNK].rstrip()}..."
        evidence_blocks.append(
            "\n".join(
                [
                    f"[Source {index}] {chunk.citation()}",
                    f"Document type: {chunk.doc_type or 'unknown'}",
                    f"Evidence: {text}",
                ]
            )
        )

    return (
        "## Retrieved Clinical Evidence\n"
        "You must answer primarily from the retrieved evidence below, not from generic medical knowledge. "
        "Use the exact care pathway, warning signs, actions, or limits described in these sources when they are relevant. "
        "If the retrieved evidence is only partially relevant, say that clearly and separate evidence-based points from general clinical context. "
        "For care-worker questions, give a direct answer first, then 3-5 practical actions or signs, and include escalation/red-flag advice. "
        "Refer to evidence using labels such as [Source 1] when relevant.\n\n"
        + "\n\n".join(evidence_blocks)
    )


def _combine_contexts(*contexts: str) -> str:
    return "\n\n".join(context.strip() for context in contexts if context and context.strip())


def _source_labels(chunks: list[RetrievedChunk]) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for chunk in chunks:
        source = _source_label(chunk)
        if source in seen:
            continue
        seen.add(source)
        labels.append(source)
    return labels


def _source_label(chunk: RetrievedChunk) -> str:
    parts = [chunk.source_filename or chunk.source_title]
    if chunk.source_title and chunk.source_title != chunk.source_filename:
        parts.append(chunk.source_title)
    if chunk.section_heading:
        parts.append(chunk.section_heading)
    parts.append(chunk.page_label())
    return " - ".join(part for part in parts if part)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("C3A_AI_PORT", "8001")),
        reload=True,
    )
