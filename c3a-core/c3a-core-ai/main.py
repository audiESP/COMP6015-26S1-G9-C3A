"""C3A Core AI service.

This service owns Ollama inference, Qdrant retrieval, and RAG citation data.
The API gateway calls this service over HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chat_router import RouteDecision, decide_route, with_effective_mode
from db_context import DbContextResult, DbContextRetriever
from logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from ollama_service import OllamaService, OllamaServiceError, UnsupportedAttachmentError
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
CHAT_RAG_TOP_K = int(os.getenv("CHAT_RAG_TOP_K", os.getenv("RAG_TOP_K", "3")))
CHAT_RAG_MAX_CHARS_PER_CHUNK = int(os.getenv("CHAT_RAG_MAX_CHARS_PER_CHUNK", "600"))
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

service = OllamaService(enabled=AI_ENABLED)
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
    pastMedicalHistory: Optional[str] = None


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


class IncidentChecklistItem(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    completed: bool = False


class AttachmentData(BaseModel):
    type: str
    base64: str
    mimeType: str


class AiChatRequest(BaseModel):
    messages: list[ChatMessage]
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    currentTaskContext: Optional[CareTaskContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    checklistContext: Optional[list[IncidentChecklistItem]] = None
    attachments: Optional[list[AttachmentData]] = None


class AiChatResponse(BaseModel):
    reply: str
    sources: list[str] = []
    rag: dict[str, Any] = {}
    model: dict[str, Any] = {}


class RiskAnalysisRequest(BaseModel):
    note: str
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    currentTaskContext: Optional[CareTaskContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None


class RiskSuggestion(BaseModel):
    riskType: str
    level: Literal["low", "moderate", "high"]
    confidence: float
    reason: str
    recommendedActions: list[str]
    requiresConfirmation: bool = True


class RiskAnalysisResponse(BaseModel):
    suggestions: list[RiskSuggestion] = []
    safetyBoundary: dict[str, bool] = {
        "diagnosisMade": False,
        "medicationChangeSuggested": False,
    }


@dataclass(frozen=True)
class PreparedChat:
    latest_user_query: str
    initial_route: RouteDecision
    effective_route: RouteDecision
    ambiguity_resolved_by: str
    rag_chunks: list[RetrievedChunk]
    accepted_rag_chunks: list[RetrievedChunk]
    rag_elapsed_ms: float
    db_context_result: DbContextResult
    db_context_elapsed_ms: float
    combined_context: str


class RagSearchRequest(BaseModel):
    query: str
    topK: Optional[int] = None


class PatientSummaryRequest(BaseModel):
    patientId: str
    patientContext: Optional[PatientContext] = None


class PatientSummaryResponse(BaseModel):
    summary: str
    patientId: str
    records: list[dict[str, Any]] = []
    database: dict[str, Any] = {}
    model: dict[str, Any] = {}


@app.on_event("startup")
async def startup_log_summary():
    await service.check_health()
    try:
        await asyncio.to_thread(db_context_retriever.open)
    except Exception as exc:
        logger.warning("PostgreSQL context pool startup failed: %s", exc)
    logger.info(
        "C3A Core AI startup port=%s debug_backend=%s ai_enabled=%s model=%s device=%s rag=%s",
        os.getenv("C3A_AI_PORT", "8001"),
        os.getenv("DEBUG_BACKEND", "").lower() == "true",
        AI_ENABLED,
        service.status().get("model"),
        service.status().get("device"),
        preview_object(rag_retriever.status()),
    )


@app.on_event("shutdown")
async def shutdown_services():
    await asyncio.gather(
        asyncio.to_thread(db_context_retriever.close),
        asyncio.to_thread(rag_retriever.close),
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


def _risk_analysis_prompt(req: RiskAnalysisRequest) -> str:
    context = {
        "patient": req.patientContext.model_dump(exclude_none=True) if req.patientContext else {},
        "worker": req.workerContext.model_dump(exclude_none=True) if req.workerContext else {},
        "visit": req.visitContext.model_dump(exclude_none=True) if req.visitContext else {},
        "current_task": req.currentTaskContext.model_dump(exclude_none=True) if req.currentTaskContext else {},
        "tasks": [item.model_dump(exclude_none=True) for item in (req.taskContext or [])],
        "events": [item.model_dump(exclude_none=True) for item in (req.eventContext or [])],
        "active_risks": [item.model_dump(exclude_none=True) for item in (req.riskContext or [])],
    }
    return (
        "Analyse the following care-worker observation as an auxiliary risk suggestion. "
        "Return JSON only, with this exact shape: "
        '{"suggestions":[{"riskType":"string","level":"low|moderate|high",'
        '"confidence":0.0,"reason":"string","recommendedActions":["string"],'
        '"requiresConfirmation":true}]}. '
        "Use only evidence in the note and supplied context. Do not diagnose, prescribe, "
        "change medication, or create/resolve an official alert. Suggestions must require "
        "human confirmation. Return an empty suggestions array when no actionable concern "
        "is supported. For medication notes, never recommend an additional dose or dose change.\n\n"
        f"Observation note:\n{req.note}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=True)}"
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Risk analysis payload is not an object")
    return payload


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
    model_status = await service.check_health()
    return {
        "status": "ok" if model_status["loaded"] else "degraded",
        "service": "c3a-core-ai",
        "model": model_status,
        "rag": rag_retriever.status(),
        "database_context": db_context_retriever.status(),
        "debug": {
            "debug_backend": os.getenv("DEBUG_BACKEND", "").lower() == "true",
            "ai_enabled": AI_ENABLED,
            "chat_uses_rag": CHAT_RAG_ENABLED,
        },
    }


@app.post("/ai/patient-summary", response_model=PatientSummaryResponse)
async def patient_summary(req: PatientSummaryRequest):
    started_at = time.perf_counter()
    logger.info("AI POST /ai/patient-summary received patient_id=%s", req.patientId)
    db_result = await db_context_retriever.patient_summary_context(req.patientId)
    if not db_result.context:
        logger.warning("AI patient summary found no database rows patient_id=%s", req.patientId)
        raise HTTPException(status_code=404, detail="No database records found for this patient")

    prompt = (
        "You are the Virtual Health Assistant for a home-care worker. "
        "Synthesise the following retrieved PostgreSQL patient data (condition, medication, "
        "allergy, encounter, observation, and CALD information) into a single concise, "
        "contextual patient summary to present to the home-care worker before or at visit start. "
        "Combine the data into one coherent response. Use only the supplied data; do not invent "
        "clinical facts. Use these short headings exactly:\n"
        "1. Overview\n2. Active Conditions\n3. Medications\n4. Allergies\n"
        "5. Recent Encounters and Observations\n6. CALD and Communication Needs\n7. Care Focus for this Visit\n\n"
        f"{db_result.context}"
    )
    try:
        summary = await service.generate_reply(
            messages=[("user", prompt)],
            patient=req.patientContext,
        )
    except OllamaServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info(
        "AI POST /ai/patient-summary completed patient_id=%s elapsed_ms=%.1f chars=%s",
        req.patientId,
        (time.perf_counter() - started_at) * 1000,
        len(summary),
    )
    return PatientSummaryResponse(
        summary=summary,
        patientId=req.patientId,
        records=db_result.metadata.get("records", []),
        database=db_result.metadata,
        model=service.status(),
    )


@app.post("/ai/chat", response_model=AiChatResponse)
async def chat(req: AiChatRequest):
    started_at = time.perf_counter()
    prepared = await _prepare_chat(req)
    latest_user_query = prepared.latest_user_query
    initial_route = prepared.initial_route
    effective_route = prepared.effective_route
    ambiguity_resolved_by = prepared.ambiguity_resolved_by
    rag_chunks = prepared.rag_chunks
    accepted_rag_chunks = prepared.accepted_rag_chunks
    rag_elapsed_ms = prepared.rag_elapsed_ms
    db_context_result = prepared.db_context_result
    db_context_elapsed_ms = prepared.db_context_elapsed_ms
    combined_context = prepared.combined_context

    generation_started_at = time.perf_counter()
    try:
        reply = await service.generate_reply(
            **_generation_kwargs(req, prepared),
        )
    except UnsupportedAttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OllamaServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
            "used_for_chat": bool(accepted_rag_chunks),
            "top_k": CHAT_RAG_TOP_K,
            "status": rag_retriever.status(),
            "database_context": db_context_result.metadata,
            "rag_context": {
                "retrieved_count": len(rag_chunks),
                "accepted_count": len(accepted_rag_chunks),
                "min_score": CHAT_RAG_MIN_SCORE,
            },
            "route": _route_payload(prepared),
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


@app.post("/ai/risk/analyse", response_model=RiskAnalysisResponse)
async def analyse_risk(req: RiskAnalysisRequest):
    note = req.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Risk note must not be empty")

    prompt = _risk_analysis_prompt(req)
    try:
        reply = await service.generate_reply(
            messages=[("user", prompt)],
            patient=req.patientContext,
            worker=req.workerContext,
            visit=req.visitContext,
            current_task=req.currentTaskContext,
            tasks=req.taskContext or [],
            events=req.eventContext or [],
            risks=req.riskContext or [],
        )
    except OllamaServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        payload = _parse_json_object(reply)
        raw_suggestions = payload.get("suggestions", [])
        if not isinstance(raw_suggestions, list):
            raise ValueError("Risk analysis suggestions are not an array")
        suggestions = [
            # The service boundary owns this invariant even if the model ignores the prompt.
            RiskSuggestion.model_validate({**item, "requiresConfirmation": True})
            for item in raw_suggestions
            if isinstance(item, dict)
        ]
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("AI risk analysis returned invalid JSON: %s", exc)
        suggestions = []

    return RiskAnalysisResponse(
        suggestions=suggestions,
        safetyBoundary={
            "diagnosisMade": False,
            "medicationChangeSuggested": False,
        },
    )


@app.post("/ai/chat/stream")
async def chat_stream(req: AiChatRequest):
    started_at = time.perf_counter()
    prepared = await _prepare_chat(req)

    async def event_stream():
        generation_started_at = time.perf_counter()
        reply_chars = 0
        try:
            async for chunk in service.stream_reply(**_generation_kwargs(req, prepared)):
                reply_chars += len(chunk)
                yield _ndjson({"type": "token", "content": chunk})
            sources = _source_labels(prepared.accepted_rag_chunks)
            yield _ndjson(
                {
                    "type": "done",
                    "sources": sources,
                    "appendSources": bool(sources)
                    and not prepared.db_context_result.metadata.get("used_for_chat"),
                    "route": _route_payload(prepared),
                    "model": service.status(),
                }
            )
            logger.info(
                "AI POST /ai/chat/stream completed route=%s rag_elapsed_ms=%.1f db_context_elapsed_ms=%.1f generation_elapsed_ms=%.1f total_elapsed_ms=%.1f reply_chars=%s",
                prepared.effective_route.mode,
                prepared.rag_elapsed_ms,
                prepared.db_context_elapsed_ms,
                (time.perf_counter() - generation_started_at) * 1000,
                (time.perf_counter() - started_at) * 1000,
                reply_chars,
            )
        except (UnsupportedAttachmentError, OllamaServiceError) as exc:
            logger.warning("AI streaming generation failed: %s", exc, exc_info=True)
            yield _ndjson({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _prepare_chat(req: AiChatRequest) -> PreparedChat:
    latest_user_query = _latest_user_query(req.messages)
    if req.attachments:
        raise HTTPException(
            status_code=422,
            detail="The configured local Llama model does not support attachments",
        )
    initial_route = decide_route(
        latest_user_query,
        req.patientContext,
        req.attachments,
        req.currentTaskContext,
    )
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

    (rag_chunks, rag_elapsed_ms), (db_context_result, db_context_elapsed_ms) = (
        await asyncio.gather(
            _retrieve_rag_context(latest_user_query, initial_route),
            _retrieve_database_context(
                latest_user_query,
                req.patientContext,
                initial_route,
            ),
        )
    )
    accepted_rag_chunks = _filter_rag_chunks(rag_chunks)
    rag_context = _build_chat_rag_context(accepted_rag_chunks)
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

    return PreparedChat(
        latest_user_query=latest_user_query,
        initial_route=initial_route,
        effective_route=effective_route,
        ambiguity_resolved_by=ambiguity_resolved_by,
        rag_chunks=rag_chunks,
        accepted_rag_chunks=accepted_rag_chunks,
        rag_elapsed_ms=rag_elapsed_ms,
        db_context_result=db_context_result,
        db_context_elapsed_ms=db_context_elapsed_ms,
        combined_context=combined_context,
    )


def _generation_kwargs(req: AiChatRequest, prepared: PreparedChat) -> dict[str, Any]:
    return {
        "messages": [(message.role, message.content) for message in req.messages],
        "patient": req.patientContext if prepared.effective_route.uses_db else None,
        "worker": req.workerContext,
        "visit": req.visitContext,
        "current_task": req.currentTaskContext,
        "tasks": req.taskContext or [],
        "events": req.eventContext or [],
        "risks": req.riskContext or [],
        "checklist": req.checklistContext or [],
        "attachments": req.attachments or [],
        "rag_context": prepared.combined_context,
    }


def _route_payload(prepared: PreparedChat) -> dict[str, Any]:
    return {
        "initial_mode": prepared.initial_route.mode,
        "effective_mode": prepared.effective_route.mode,
        "uses_db": prepared.effective_route.uses_db,
        "uses_rag": prepared.effective_route.uses_rag,
        "confidence": prepared.initial_route.confidence,
        "reason": prepared.initial_route.reason,
        "matched_signals": prepared.initial_route.matched_signals,
        "ambiguity_resolved_by": prepared.ambiguity_resolved_by,
    }


def _ndjson(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


async def _retrieve_rag_context(
    query: str,
    route: RouteDecision,
) -> tuple[list[RetrievedChunk], float]:
    started_at = time.perf_counter()
    chunks: list[RetrievedChunk] = []
    if route.uses_rag and CHAT_RAG_ENABLED and query.strip() and rag_retriever.is_configured:
        chunks = await _retrieve_for_chat(query)
    else:
        logger.info(
            "AI POST /ai/chat RAG skipped route_uses_rag=%s enabled=%s configured=%s query_present=%s",
            route.uses_rag,
            CHAT_RAG_ENABLED,
            rag_retriever.is_configured,
            bool(query.strip()),
        )
    return chunks, (time.perf_counter() - started_at) * 1000


async def _retrieve_database_context(
    query: str,
    patient_context,
    route: RouteDecision,
) -> tuple[DbContextResult, float]:
    started_at = time.perf_counter()
    if route.uses_db:
        result = await db_context_retriever.retrieve(
            query,
            patient_context=patient_context,
        )
    else:
        logger.info(
            "AI POST /ai/chat PostgreSQL context skipped route_uses_db=%s",
            route.uses_db,
        )
        result = _empty_db_context_result()
    return result, (time.perf_counter() - started_at) * 1000


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
