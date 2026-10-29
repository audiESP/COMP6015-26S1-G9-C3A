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
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from chat_router import PATIENT_ANCHOR_PHRASES, RouteDecision, decide_route, with_effective_mode
from db_context import DbContextResult, DbContextRetriever
from logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from ollama_service import OllamaService, OllamaServiceError, UnsupportedAttachmentError
from rag.citations import RetrievedChunk
from rag.retriever import RagRetriever
from web_search import WebSearchService, build_task_queries


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
TASK_MATERIALS_MIN_INTERNAL_RESULTS = int(os.getenv("TASK_MATERIALS_MIN_INTERNAL_RESULTS", "2"))
TASK_MATERIALS_MIN_SCORE = float(os.getenv("TASK_MATERIALS_MIN_SCORE", "0.25"))
TASK_MATERIALS_WEB_MAX_RESULTS = int(os.getenv("TASK_MATERIALS_WEB_MAX_RESULTS", "3"))

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
web_search_service = WebSearchService()
SPEECH_SERVICE_URL = os.getenv("SPEECH_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")
SPEECH_SERVICE_TIMEOUT_SECONDS = float(os.getenv("SPEECH_SERVICE_TIMEOUT_SECONDS", "120"))


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


class MedicationSupportContext(BaseModel):
    id: Optional[str] = None
    visitId: Optional[str] = None
    taskId: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    timestamp: Optional[str] = None
    hcwId: Optional[str] = None
    medicationNames: list[str] = Field(default_factory=list)
    medicationItems: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioEventContext(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    note: Optional[str] = None


class RiskContext(BaseModel):
    id: Optional[str] = None
    alertKey: Optional[str] = None
    riskType: Optional[str] = None
    level: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    visitId: Optional[str] = None
    assignedWorkerId: Optional[str] = None
    generatedFromEventId: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    acknowledgedAt: Optional[str] = None
    acknowledgedByWorkerId: Optional[str] = None
    resolvedAt: Optional[str] = None
    resolvedByWorkerId: Optional[str] = None
    dismissedAt: Optional[str] = None
    dismissedByWorkerId: Optional[str] = None
    reviewNote: Optional[str] = None


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
    medicationSupportContext: Optional[MedicationSupportContext] = None
    eventContext: Optional[list[ScenarioEventContext]] = None
    riskContext: Optional[list[RiskContext]] = None
    checklistContext: Optional[list[IncidentChecklistItem]] = None
    attachments: Optional[list[AttachmentData]] = None
    responseWordLimit: Optional[int] = 250


class SourceReference(BaseModel):
    id: str
    kind: Literal["guideline", "patient_record", "visit_context", "general_knowledge"]
    label: str
    reason: str
    documentTitle: Optional[str] = None
    filename: Optional[str] = None
    pageStart: Optional[int] = None
    pageEnd: Optional[int] = None
    section: Optional[str] = None
    recordTypes: list[str] = Field(default_factory=list)


class AiChatResponse(BaseModel):
    reply: str
    sources: list[str] = Field(default_factory=list)
    sourceReferences: list[SourceReference] = Field(default_factory=list)
    rag: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)


class TranslationRequest(BaseModel):
    text: str
    sourceLanguage: Optional[str] = None
    targetLanguage: str


class TranslationResponse(BaseModel):
    sourceLanguage: str
    targetLanguage: str
    translatedText: str


class SpeechTranscriptionResponse(BaseModel):
    transcript: str
    sourceLanguage: str
    speakerRole: Literal["care_worker", "patient"]
    model: str
    requiresHumanReview: bool = True
    audioRetained: bool = False


class RiskAnalysisRequest(BaseModel):
    note: str
    patientContext: Optional[PatientContext] = None
    workerContext: Optional[WorkerContext] = None
    visitContext: Optional[VisitContext] = None
    currentTaskContext: Optional[CareTaskContext] = None
    taskContext: Optional[list[CareTaskContext]] = None
    medicationSupportContext: Optional[MedicationSupportContext] = None
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


class TaskMaterialsRequest(BaseModel):
    taskLabel: str
    taskDetail: Optional[str] = None
    taskType: Optional[str] = None


class TaskMaterialItem(BaseModel):
    sourceType: Literal["internal", "web"]
    title: str
    snippet: str
    url: Optional[str] = None
    documentTitle: Optional[str] = None
    section: Optional[str] = None
    pageLabel: Optional[str] = None
    score: Optional[float] = None


class TaskMaterialsResponse(BaseModel):
    query: str
    items: list[TaskMaterialItem] = Field(default_factory=list)
    usedWebSearch: bool = False
    internalCount: int = 0
    webCount: int = 0


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


def _is_visit_report_generation(query: str) -> bool:
    lowered = query.casefold()
    return "visit report" in lowered and any(
        term in lowered for term in ("generate", "create", "write", "draft")
    )


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
        "medication_support": req.medicationSupportContext.model_dump(exclude_none=True) if req.medicationSupportContext else {},
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
                "evidence_excerpt": _rag_evidence_text(chunk),
            }
            for chunk in chunks
        ]
    }


@app.get("/ai/health")
async def health():
    model_status = await service.check_health()
    speech_status = await _speech_health()
    return {
        "status": "ok" if model_status["loaded"] else "degraded",
        "service": "c3a-core-ai",
        "model": model_status,
        "rag": rag_retriever.status(),
        "web_search": web_search_service.status(),
        "database_context": db_context_retriever.status(),
        "speech": speech_status,
        "debug": {
            "debug_backend": os.getenv("DEBUG_BACKEND", "").lower() == "true",
            "ai_enabled": AI_ENABLED,
            "chat_uses_rag": CHAT_RAG_ENABLED,
        },
    }


@app.post("/ai/speech/transcribe", response_model=SpeechTranscriptionResponse)
async def transcribe_speech(
    audio: UploadFile = File(...),
    sourceLanguage: str = Form(...),
    speakerRole: Literal["care_worker", "patient"] = Form(...),
    clientRequestId: str | None = Form(None),
):
    if not sourceLanguage.strip():
        raise HTTPException(status_code=400, detail="Source language must not be empty")
    content_type = audio.content_type or ""
    max_bytes = int(os.getenv("SPEECH_MAX_UPLOAD_BYTES", "10485760"))
    data = await audio.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Audio recording must not be empty")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio recording exceeds the upload limit")
    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=SPEECH_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{SPEECH_SERVICE_URL}/transcribe",
                files={"audio": (audio.filename or "utterance.m4a", data, content_type)},
                data={"sourceLanguage": sourceLanguage},
            )
            if response.status_code >= 400:
                detail = response.json().get("detail", "Speech recognition failed")
                raise HTTPException(status_code=response.status_code if response.status_code < 500 else 503, detail=detail)
            payload = response.json()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.warning("Speech container unavailable request_id=%s error=%s", clientRequestId, exc)
        raise HTTPException(status_code=503, detail="Speech recognition service is unavailable") from exc
    logger.info(
        "AI speech transcribed request_id=%s language=%s role=%s duration_ms=%s transcript_chars=%s elapsed_ms=%.1f",
        clientRequestId, sourceLanguage, speakerRole, payload.get("durationMs"), len(payload.get("transcript", "")), (time.perf_counter() - started_at) * 1000,
    )
    return SpeechTranscriptionResponse(
        transcript=payload["transcript"], sourceLanguage=sourceLanguage, speakerRole=speakerRole, model=payload.get("model", "whisper-base-int8"),
    )


async def _speech_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SPEECH_SERVICE_URL}/health")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        return {"enabled": False, "loaded": False, "container": "unavailable", "error": type(exc).__name__}


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
    direct_reply = _direct_reply(req)
    if direct_reply is not None:
        reply = direct_reply
    else:
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
    if direct_reply is not None:
        rag_payload["used_for_chat"] = False
        rag_payload["answer_method"] = "structured_current_record"
    response = AiChatResponse(
        reply=reply,
        sources=[] if direct_reply is not None else _source_labels(_cited_chunks(accepted_rag_chunks, reply)),
        sourceReferences=_current_record_sources(req) if direct_reply is not None else _source_references(req, prepared, reply),
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
            medication_support=req.medicationSupportContext,
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
    direct_reply = _direct_reply(req)

    async def event_stream():
        generation_started_at = time.perf_counter()
        reply_parts: list[str] = []
        try:
            if direct_reply is not None:
                reply_parts.append(direct_reply)
                yield _ndjson({"type": "token", "content": direct_reply})
            else:
                async for chunk in service.stream_reply(**_generation_kwargs(req, prepared)):
                    reply_parts.append(chunk)
                    yield _ndjson({"type": "token", "content": chunk})
            reply = "".join(reply_parts)
            sources = [] if direct_reply is not None else _source_labels(_cited_chunks(prepared.accepted_rag_chunks, reply))
            yield _ndjson(
                {
                    "type": "done",
                    "sources": sources,
                    "sourceReferences": [
                        item.model_dump(exclude_none=True)
                        for item in (_current_record_sources(req) if direct_reply is not None else _source_references(req, prepared, reply))
                    ],
                    "appendSources": bool(sources),
                    "route": _route_payload(prepared),
                    "model": service.status(),
                    "answerMethod": "structured_current_record" if direct_reply is not None else "model",
                }
            )
            logger.info(
                "AI POST /ai/chat/stream completed route=%s rag_elapsed_ms=%.1f db_context_elapsed_ms=%.1f generation_elapsed_ms=%.1f total_elapsed_ms=%.1f reply_chars=%s",
                prepared.effective_route.mode,
                prepared.rag_elapsed_ms,
                prepared.db_context_elapsed_ms,
                (time.perf_counter() - generation_started_at) * 1000,
                (time.perf_counter() - started_at) * 1000,
                len(reply),
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


@app.post("/ai/translate", response_model=TranslationResponse)
async def translate(req: TranslationRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text to translate must not be empty")
    if not req.targetLanguage.strip():
        raise HTTPException(status_code=400, detail="Target language must not be empty")

    started_at = time.perf_counter()
    logger.info(
        "AI POST /ai/translate received target_language=%s source_language=%s text_preview=%r",
        req.targetLanguage,
        req.sourceLanguage or "auto",
        _preview(req.text),
    )
    try:
        result = await service.translate_text(
            text=req.text,
            target_language=req.targetLanguage,
            source_language=req.sourceLanguage,
        )
    except OllamaServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info(
        "AI POST /ai/translate completed elapsed_ms=%.1f source_language=%s translated_chars=%s",
        (time.perf_counter() - started_at) * 1000,
        result["sourceLanguage"],
        len(result["translatedText"]),
    )
    return TranslationResponse(**result)


async def _prepare_chat(req: AiChatRequest) -> PreparedChat:
    latest_user_query = _latest_user_query(req.messages)
    if req.attachments:
        raise HTTPException(
            status_code=422,
            detail="The configured local Llama model does not support attachments",
        )
    if _is_visit_report_generation(latest_user_query):
        # The report request already carries the complete visit record. External
        # database or guideline retrieval could mix unrelated facts into it.
        initial_route = RouteDecision(
            mode="direct_ai",
            uses_db=False,
            uses_rag=False,
            confidence=1.0,
            reason="Visit report generation uses only the supplied visit record.",
            matched_signals=["visit_report_generation"],
        )
    else:
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
    accepted_rag_chunks = _filter_rag_chunks(rag_chunks, req, latest_user_query)
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
        # Supplied visit context is independent of whether PostgreSQL was queried.
        "patient": req.patientContext,
        "worker": req.workerContext,
        "visit": req.visitContext,
        "current_task": req.currentTaskContext,
        "tasks": req.taskContext or [],
        "medication_support": req.medicationSupportContext,
        "events": req.eventContext or [],
        "risks": req.riskContext or [],
        "checklist": req.checklistContext or [],
        "attachments": req.attachments or [],
        "rag_context": prepared.combined_context,
        "response_word_limit": req.responseWordLimit if req.responseWordLimit and req.responseWordLimit > 0 else None,
    }


def _direct_reply(req: AiChatRequest) -> str | None:
    """Return a structured answer when the question can be answered from fields alone."""
    # Visit reports are broad generation requests. Their prompts mention narrow
    # fields such as medication-support "outcome" and "record", but must not be
    # collapsed into one of the deterministic single-field answers below.
    if _is_visit_report_generation(_latest_user_query(req.messages)):
        return None
    return (
        _missing_patient_reply(req)
        or _current_record_reply(req)
        or _factual_record_reply(req)
        or _medication_support_record_reply(req)
        or _task_timing_reply(req)
        or _recorded_risk_reply(req)
    )


def _missing_patient_reply(req: AiChatRequest) -> str | None:
    """Refuse patient-specific answers when no patient is linked.

    Without this, retrieved guidance can be presented as if it described the
    unlinked patient (for example, asserting delirium from a delirium standard).
    """
    if req.patientContext is not None:
        return None
    latest = _latest_user_query(req.messages).casefold()
    if not any(phrase in latest for phrase in PATIENT_ANCHOR_PHRASES):
        return None
    return (
        "No patient record is linked to this chat, so the patient-specific answer cannot be determined. "
        "Link the patient or open their visit, then ask again."
    )


def _is_current_record_refresh(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        re.search(r"\b(?:linked|patient|current|updated) record\b", lowered)
        and re.search(r"\b(?:updated|now|current|latest)\b", lowered)
    ) or ("记录" in text and any(word in text for word in ("更新", "最新", "现在")))


def _current_record_reply(req: AiChatRequest) -> str | None:
    """Answer narrow current-state refreshes from this request's structured facts.

    Earlier assistant text is not an earlier structured record. We therefore
    report the current value, never infer which field changed from that text.
    """
    user_turns = [message.content for message in req.messages if message.role == "user"]
    if len(user_turns) < 2 or not _is_current_record_refresh(user_turns[-1]):
        return None
    latest = user_turns[-1].casefold()
    if (re.search(r"\b(?:what should i do|how should i|advise|recommend|next steps)\b", latest)
            or any(term in latest for term in ("怎么做", "怎么办", "建议"))):
        return None
    original = next((text for text in reversed(user_turns[:-1])
                     if not _is_current_record_refresh(text)), None)
    if not original:
        return None
    question = original.casefold()
    patient = req.patientContext
    answer: str | None = None
    if "medication support" in question or "medicine support" in question:
        support = req.medicationSupportContext
        if support and support.status:
            names = ", ".join(support.medicationNames)
            answer = f"The current medication-support outcome is {support.status}."
            if names:
                answer += f" The support record lists {names}."
            answer += " This status alone does not confirm that any medicine was taken."
    elif any(term in question for term in ("risk", "alert", "delirium", "falls")):
        if req.riskContext is not None:
            active = [risk for risk in req.riskContext
                      if (risk.status or "active").casefold() not in {"resolved", "dismissed"}]
            historical = [risk for risk in req.riskContext
                          if (risk.status or "active").casefold() in {"resolved", "dismissed"}]
            if active:
                answer = "Current active risk alerts: " + "; ".join(
                    f"{risk.title or risk.riskType or 'Unlabelled alert'} ({risk.status or 'active'})"
                    for risk in active) + "."
            else:
                answer = "No active risk alert is recorded in the supplied current context."
            if historical:
                answer += " Historical alerts: " + "; ".join(
                    f"{risk.title or risk.riskType or 'Unlabelled alert'} ({risk.status})"
                    for risk in historical) + "."
    elif any(term in question for term in ("mobility", "walker", "wheelchair", "walking", "transfer")):
        if patient and patient.mobilitySupport:
            answer = f"The current record lists mobility support as {patient.mobilitySupport}."
    elif "task" in question:
        task = req.currentTaskContext
        if task and task.status:
            answer = f"The current task is {task.status}."
            if task.label:
                answer += f" Task: {task.label}."
    elif any(term in question for term in ("communication", "interpreter", "language")):
        if patient:
            facts = []
            if patient.preferredLanguage:
                facts.append(f"preferred language: {patient.preferredLanguage}")
            if patient.interpreterRequired is True:
                facts.append("interpreter marked required")
            elif patient.interpreterRequired is False:
                facts.append("interpreter not marked required")
            if patient.communicationNotes and patient.communicationNotes != "No special communication note.":
                facts.append(f"communication notes: {patient.communicationNotes}")
            if facts:
                answer = "The current record says " + "; ".join(facts) + "."
    elif "allerg" in question:
        if patient and patient.allergies is not None:
            answer = ("The current record lists these allergies: " + ", ".join(patient.allergies) + "."
                      if patient.allergies else "No allergy is recorded in the supplied current record.")
    elif any(term in question for term in ("medicine", "medication", "drug")):
        if patient and patient.medications is not None:
            answer = ("The current record lists these medicines: " + ", ".join(patient.medications) + "."
                      if patient.medications else "No medicine is recorded in the supplied current record.")
    if answer and re.search(r"\b(?:what changed|which fields changed|difference|compare)\b", user_turns[-1].casefold()):
        answer = "An earlier structured record was not supplied, so I cannot verify the exact change. " + answer
    return answer


def _factual_record_reply(req: AiChatRequest) -> str | None:
    """Answer narrowly phrased record questions without inferring missing facts.

    This path intentionally excludes advice, documentation instructions, and
    broad summaries: those still need the normal generation path.
    """
    user_turns = [message.content for message in req.messages if message.role == "user"]
    if len(user_turns) != 1:
        return None
    question = user_turns[0].strip().casefold()
    if not question or any(term in question for term in (
        "how should", "what should", "advise", "recommend", "plan ", "summarize", "explain", "why ",
    )):
        return None
    patient = req.patientContext
    support = req.medicationSupportContext
    if any(term in question for term in ("medication support", "medicine support")):
        if "took" in question or "taken" in question or "administered" in question:
            return _medication_ingestion_reply(support)
        if any(term in question for term in ("outcome", "status", "recorded")):
            if not support or not support.status:
                return "The medication-support outcome is not established in the supplied record."
            answer = f"The recorded medication-support outcome is {support.status}."
            if support.medicationNames:
                answer += " The support record lists " + ", ".join(support.medicationNames) + "."
            return answer + " This support status alone does not confirm whether medicine was taken."
    if ("took" in question or "taken" in question or "administered" in question) and any(
        term in question for term in ("medicine", "medication", "drug")
    ):
        return _medication_ingestion_reply(support)
    if "interpreter" in question and any(term in question for term in ("require", "needed", "need ")):
        if not patient or patient.interpreterRequired is None:
            return "The supplied record does not establish whether this patient requires an interpreter."
        return ("Interpreter support is marked required in the supplied record."
                if patient.interpreterRequired else
                "Interpreter support is marked not required in the supplied record.")
    if "communication support" in question or "communication preference" in question:
        if not patient:
            return "No linked patient communication record was supplied, so the patient-specific support is unknown."
        facts = []
        if patient.preferredLanguage:
            facts.append(f"preferred language: {patient.preferredLanguage}")
        if patient.interpreterRequired is not None:
            facts.append("interpreter required: " + ("yes" if patient.interpreterRequired else "no"))
        if patient.communicationNotes and patient.communicationNotes != "No special communication note.":
            facts.append(f"communication notes: {patient.communicationNotes.rstrip('.')}")
        return ("The supplied record says " + "; ".join(facts) + "." if facts else
                "No patient-specific communication preference is recorded in the supplied context.")
    if "preferred language" in question:
        return (f"The recorded preferred language is {patient.preferredLanguage}."
                if patient and patient.preferredLanguage else
                "The patient's preferred language is not established in the supplied record.")
    if ("medicine" in question or "medication" in question) and not any(
        term in question for term in ("risk", "alert", "support", "task", "visit")
    ):
        if "recorded" in question and support is None:
            if not patient or patient.medications is None:
                return "The patient's medicines are not established in the supplied record."
            return ("The record lists these medicines: " + ", ".join(patient.medications) +
                    ". This list does not confirm they were taken." if patient.medications else
                    "No medicine is listed in the supplied patient record; this does not establish whether any was taken.")
    if "allerg" in question and "recorded" in question:
        if not patient or patient.allergies is None:
            return "The patient's allergy status is not established in the supplied record."
        return ("The record lists these allergies: " + ", ".join(patient.allergies) + "."
                if patient.allergies else "No allergy is listed in the supplied patient record.")
    if "mobility support" in question and "recorded" in question:
        return (f"The recorded mobility support is {patient.mobilitySupport}."
                if patient and patient.mobilitySupport else
                "The patient's mobility support is not established in the supplied record.")
    if "which patient" in question and "linked" in question:
        return (f"The linked patient is {patient.name}." if patient and patient.name else
                "No patient identity is established by the supplied context.")
    return None


def _medication_ingestion_reply(support: MedicationSupportContext | None) -> str:
    items = support.medicationItems if support else None
    confirmed = [item for item in (items or []) if str(item.get("takenStatus", "")).casefold() in
                 {"taken", "administered", "yes", "confirmed"}]
    if confirmed:
        names = [str(item.get("name") or item.get("medicationName") or "medicine") for item in confirmed]
        return "Item-level taken status confirms: " + ", ".join(names) + "."
    outcome = f"The medication-support outcome is recorded as {support.status}. " if support and support.status else ""
    return (outcome + "The supplied medication-support record does not confirm whether the medicine was taken. "
            "A support outcome or medicine list alone is not proof of ingestion.")


MEDICATION_SUPPORT_NEXT_STEP = {
    "completed": "Record that support was completed; record the medicine as taken only if intake was confirmed item by item.",
    "declined": "Record that the patient declined support and report it to the care coordinator or nurse under your organisation's process.",
    "delayed": "Record the delay and when support will be offered, and report it if the medicine is time-critical.",
    "unable to confirm": "Record that intake could not be confirmed and report it to the care coordinator or nurse.",
    "unavailable": "Record that the medicine was unavailable and report it so supply can be arranged.",
}


def _medication_support_record_reply(req: AiChatRequest) -> str | None:
    """Summarise or document the medication-support record from its fields.

    The model tended to report the separate wellbeing task status as the
    medication-support outcome, so these questions are answered directly.
    """
    user_turns = [message.content for message in req.messages if message.role == "user"]
    if len(user_turns) != 1:
        return None
    question = user_turns[0].casefold()
    if not any(term in question for term in ("medication support", "medicine support")):
        return None
    summarise = any(term in question for term in ("summar", "overview"))
    document = "document" in question or "record about" in question
    if not (summarise or document):
        return None
    support = req.medicationSupportContext
    if not support or not support.status:
        return "No medication-support record is supplied for this visit, so its outcome cannot be determined."
    names = ", ".join(support.medicationNames) or "no medicine listed"
    caution = "This support status does not confirm that any medicine was taken."
    if summarise:
        reply = f"Medication-support record: outcome {support.status}; medicines listed: {names}."
        if support.notes:
            reply += f" Notes: {support.notes}"
        return f"{reply} {caution}"
    next_step = MEDICATION_SUPPORT_NEXT_STEP.get(support.status.casefold(), "Record the outcome exactly as observed.")
    return (f"Document that medication support for {names} was recorded as {support.status}. "
            f"{next_step} {caution}")


def _task_timing_reply(req: AiChatRequest) -> str | None:
    """Answer on-time questions without inferring a delay from a pending status."""
    user_turns = [message.content for message in req.messages if message.role == "user"]
    if len(user_turns) != 1:
        return None
    question = user_turns[0].casefold()
    if "task" not in question or not any(term in question for term in ("on time", "overdue", "running late", "behind schedule")):
        return None
    task = req.currentTaskContext
    if not task or not task.status:
        return "No current task status is supplied, so whether the task is on time cannot be determined."
    status = task.status.casefold()
    if status == "delayed":
        return "The current task is recorded as delayed, so it is not on time."
    if status == "completed":
        return "The current task is recorded as completed."
    if task.dueAt:
        return (f"The current task is {task.status} and due at {task.dueAt}. "
                "Compare the due time with the current time; no delay is recorded.")
    return (f"The current task is {task.status}. No due time or delay is recorded, "
            "so the record does not show whether it is on time.")


def _recorded_risk_reply(req: AiChatRequest) -> str | None:
    """List recorded risk flags and active alerts instead of inferring risk from mobility support."""
    user_turns = [message.content for message in req.messages if message.role == "user"]
    if len(user_turns) != 1:
        return None
    question = user_turns[0].casefold()
    if not ("risk" in question and "recorded" in question) or any(
        term in question for term in ("how should", "what should", "advise", "recommend")
    ):
        return None
    patient = req.patientContext
    if patient is None:
        return None
    flags = list(patient.careRiskFlags or [])
    active = [risk.title or risk.riskType or "Unlabelled alert" for risk in (req.riskContext or [])
              if (risk.status or "active").casefold() not in {"resolved", "dismissed"}]
    if not flags and not active:
        return ("No care risk flag or active risk alert is recorded in the supplied context. "
                "This does not rule out risk; report any concern you observe.")
    parts = []
    if flags:
        parts.append("Recorded care risk flags: " + ", ".join(flags) + ".")
    if active:
        parts.append("Active risk alerts: " + ", ".join(active) + ".")
    return " ".join(parts)


def _current_record_sources(req: AiChatRequest) -> list[SourceReference]:
    context_types = _supplied_context_types(req, True)
    if not context_types:
        return []
    return [SourceReference(
        id="visit-context", kind="visit_context", label="Current supplied record",
        reason="Answer computed from the structured context supplied with this request.",
        recordTypes=context_types,
    )]


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


@app.post("/ai/training/task-materials", response_model=TaskMaterialsResponse)
async def task_materials(req: TaskMaterialsRequest):
    query = " ".join(part for part in [req.taskLabel, req.taskDetail] if part and part.strip()).strip()
    if not query:
        raise HTTPException(status_code=400, detail="taskLabel must not be empty")

    logger.info("AI POST /ai/training/task-materials received query_preview=%r", _preview(query))

    internal_chunks: list[RetrievedChunk] = []
    if rag_retriever.is_configured:
        internal_chunks = await rag_retriever.retrieve(query)
    strong_internal = [chunk for chunk in internal_chunks if chunk.score >= TASK_MATERIALS_MIN_SCORE]

    items = [
        TaskMaterialItem(
            sourceType="internal",
            title=_source_label(chunk),
            snippet=_query_preview(chunk.text, query),
            documentTitle=chunk.source_title or None,
            section=chunk.section_heading or None,
            pageLabel=chunk.page_label(),
            score=chunk.score,
        )
        for chunk in strong_internal
    ]

    used_web_search = False
    web_count = 0
    if len(strong_internal) < TASK_MATERIALS_MIN_INTERNAL_RESULTS:
        # The full label+detail sentence contains generic instructional words
        # ("Check", "Review") that derail a web search engine, and task-phrased
        # queries ("... for aged care home visits") return provider policy
        # pages. Embeddings-based internal RAG above keeps using the full
        # detail; the web search instead uses symptom-oriented queries chosen
        # from the task's topics (see build_task_queries).
        web_queries = build_task_queries(req.taskLabel, req.taskDetail, req.taskType)
        web_results = await web_search_service.search(
            web_queries,
            task_context=query,
            max_results=TASK_MATERIALS_WEB_MAX_RESULTS,
        )
        web_count = len(web_results)
        used_web_search = bool(web_results)
        items.extend(
            TaskMaterialItem(
                sourceType="web",
                title=result.title,
                snippet=result.snippet,
                url=result.url,
            )
            for result in web_results
        )

    logger.info(
        "AI POST /ai/training/task-materials completed internal=%s web=%s used_web_search=%s",
        len(strong_internal),
        web_count,
        used_web_search,
    )
    return TaskMaterialsResponse(
        query=query,
        items=items,
        usedWebSearch=used_web_search,
        internalCount=len(strong_internal),
        webCount=web_count,
    )


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


# Guidance written for one condition is only accepted when that condition is in
# the question or the linked record; otherwise it is presented as patient fact.
CONDITION_SPECIFIC_SOURCES = {
    "delirium": ("delirium", "confus", "cognit", "orientation", "agitat", "disorient"),
}


def _filter_rag_chunks(
    chunks: list[RetrievedChunk],
    req: AiChatRequest | None = None,
    query: str = "",
) -> list[RetrievedChunk]:
    if CHAT_RAG_MIN_SCORE > 0:
        chunks = [chunk for chunk in chunks if chunk.score >= CHAT_RAG_MIN_SCORE]
    context_text = _condition_context_text(req, query)
    return [chunk for chunk in chunks if _condition_source_applies(chunk, context_text)]


def _condition_context_text(req: AiChatRequest | None, query: str) -> str:
    parts = [query]
    patient = req.patientContext if req else None
    if patient:
        parts += [patient.diagnosis or "", patient.cognitiveStatus or "", patient.notes or "",
                  patient.pastMedicalHistory or "", " ".join(patient.careRiskFlags or [])]
    for risk in (req.riskContext or []) if req else []:
        if (risk.status or "active").casefold() not in {"resolved", "dismissed"}:
            parts += [risk.title or "", risk.riskType or "", risk.message or ""]
    return " ".join(parts).casefold()


def _condition_source_applies(chunk: RetrievedChunk, context_text: str) -> bool:
    title = f"{chunk.source_title or ''} {chunk.source_filename or ''}".casefold()
    for condition, cues in CONDITION_SPECIFIC_SOURCES.items():
        if condition in title and not any(cue in context_text for cue in cues):
            return False
    return True


def _cited_chunks(chunks: list[RetrievedChunk], reply: str) -> list[RetrievedChunk]:
    """Keep only retrieved chunks whose [Source N] label appears in the reply."""
    cited = {int(number) for number in re.findall(r"\[Source (\d+)\]", reply or "")}
    return [chunk for index, chunk in enumerate(chunks, start=1) if index in cited]


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
            "No matching PostgreSQL rows were retrieved for this question. "
            "If structured patient or visit facts were supplied in this request, use those facts; "
            "the absent database row does not invalidate them. Do not invent additional patient facts. "
            "Only say the patient-specific answer is unknown when neither the supplied context nor a linked record establishes it."
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
        text = _rag_evidence_text(chunk)
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
        "Use retrieved evidence below only for claims it directly supports; the supplied patient and workflow fields remain the source for individual facts. "
        "Use the exact care pathway, warning signs, actions, or limits described in these sources when they are relevant. "
        "If the retrieved evidence is only partially relevant, say that clearly and separate evidence-based points from general clinical context. "
        "Give a direct answer first. Add practical actions or escalation advice only when the question asks what to do, "
        "and only actions that fit this patient's recorded needs. Do not apply guidance written for a condition "
        "(for example delirium) unless that condition is recorded for the patient or asked about. "
        "Refer to evidence using labels such as [Source 1] when relevant.\n\n"
        + "\n\n".join(evidence_blocks)
    )


def _rag_evidence_text(chunk: RetrievedChunk) -> str:
    """Return the exact excerpt passed to the generator for this chunk."""
    text = " ".join(chunk.text.split())
    if len(text) > CHAT_RAG_MAX_CHARS_PER_CHUNK:
        return f"{text[:CHAT_RAG_MAX_CHARS_PER_CHUNK].rstrip()}..."
    return text


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


def _source_references(req: AiChatRequest, prepared: PreparedChat, reply: str) -> list[SourceReference]:
    # Label numbers follow the prompt order, so keep the original index of each cited chunk.
    cited = {id(chunk) for chunk in _cited_chunks(prepared.accepted_rag_chunks, reply)}
    references = [
        SourceReference(
            id=f"guideline-{index}",
            kind="guideline",
            label=_source_label(chunk),
            reason="Retrieved as relevant clinical or care guidance for this answer.",
            documentTitle=chunk.source_title or None,
            filename=chunk.source_filename or None,
            pageStart=chunk.page_start,
            pageEnd=chunk.page_end,
            section=chunk.section_heading or None,
        )
        for index, chunk in enumerate(prepared.accepted_rag_chunks, start=1)
        if id(chunk) in cited
    ]

    db_metadata = prepared.db_context_result.metadata
    if db_metadata.get("used_for_chat"):
        record_types = [
            _friendly_record_type(intent)
            for intent in db_metadata.get("matched_intents", [])
        ]
        references.append(
            SourceReference(
                id="patient-record",
                kind="patient_record",
                label="Linked patient record",
                reason="Used matching synthetic patient records to answer the patient-specific part of the question.",
                recordTypes=list(dict.fromkeys(record_types)),
            )
        )

    context_types = _supplied_context_types(req, True)
    if context_types:
        references.append(
            SourceReference(
                id="visit-context",
                kind="visit_context",
                label="Current visit context",
                reason=f"Used the supplied {', '.join(context_types)} to tailor the response to this visit.",
                recordTypes=context_types,
            )
        )

    if not cited and not db_metadata.get("used_for_chat"):
        references.append(
            SourceReference(
                id="general-knowledge",
                kind="general_knowledge",
                label=f"General guidance from {service.status().get('model', 'the configured model')}",
                reason="No matching project guideline or patient database evidence was used; the answer relies on the configured model and any supplied visit context.",
            )
        )
    return references


def _friendly_record_type(intent: str) -> str:
    return {
        "patients": "patient profile",
        "conditions": "conditions",
        "medications": "medications",
        "allergies": "allergies",
        "encounters": "encounters",
        "observations": "observations",
        "cald_profiles": "cultural and communication profile",
    }.get(intent, intent.replace("_", " "))


def _supplied_context_types(req: AiChatRequest, include_patient: bool) -> list[str]:
    candidates = [
        (include_patient and req.patientContext is not None, "patient profile"),
        (req.workerContext is not None, "worker role"),
        (req.visitContext is not None, "visit details"),
        (req.currentTaskContext is not None or bool(req.taskContext), "care tasks"),
        (req.medicationSupportContext is not None, "medication support record"),
        (bool(req.eventContext), "recent events"),
        (bool(req.riskContext), "risk alerts and their recorded statuses"),
        (bool(req.checklistContext), "incident checklist"),
    ]
    return [label for present, label in candidates if present]


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
