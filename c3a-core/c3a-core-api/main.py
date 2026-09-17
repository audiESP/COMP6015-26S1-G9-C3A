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
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, Optional

import uvicorn
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.ai_client import AiClient, AiServiceUnavailable
from app.db import DatabaseHealthChecker, close_database_pool, open_database_pool
from app.logging_utils import add_exception_handlers, add_http_logging_middleware, preview_object
from app.repositories.training_repository import (
    TrainingRepository,
    TrainingRepositoryUnavailable,
    TrainingTopicNotFoundError,
)
from app.repositories.visit_repository import (
    VisitAccessError,
    VisitNotFoundError,
    VisitRepository,
    VisitRepositoryUnavailable,
    VisitValidationError,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    AlertActionRequest,
    CompleteVisitRequest,
    GenerateVisitReportRequest,
    GenerateVisitReportResponse,
    MedicationSupportRequest,
    PatientSummaryResponse,
    ScenarioResponse,
    RiskAnalysisRequest,
    RiskAnalysisResponse,
    ShiftSummaryResponse,
    StartVisitRequest,
    TaskIssueRequest,
    TaskMaterialsRequest,
    TaskMaterialsResponse,
    TaskStatusRequest,
    TrainingMaterialsResponse,
    TrainingSearchResponse,
    TrainingTopicsResponse,
    TranslationRequest,
    TranslationResponse,
    SpeechTranscriptionResponse,
    UpdatePatientProfileRequest,
    UploadRequest,
    UploadResponse,
    VisitQueueResponse,
)


load_dotenv()

LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG_BACKEND", "").lower() == "true" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_database_pool()
    logger.info(
        "C3A Core API startup port=%s debug_backend=%s ai_base_url=%s ai_timeout_seconds=%s database_configured=%s",
        os.getenv("C3A_API_PORT", "8000"),
        os.getenv("DEBUG_BACKEND", "").lower() == "true",
        ai_client.base_url,
        ai_client.timeout,
        database_health_checker.configured,
    )
    try:
        yield
    finally:
        close_database_pool()


app = FastAPI(title="C3A Core API", version="1.0.0", lifespan=lifespan)
ai_client = AiClient()
database_health_checker = DatabaseHealthChecker()
visit_repository = VisitRepository()
training_repository = TrainingRepository()

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


def _visit_report_prompt(req: GenerateVisitReportRequest) -> str:
    return (
        "Generate a standardised home-care visit report for records. "
        "Use only the supplied form answers, vitals, observations, visit context, "
        "tasks, events, and risk alerts. Do not invent clinical facts. "
        "Write concise professional English for HCW review. "
        "Complete every section below; do not stop before Overall Outcome. "
        "Use this structure exactly:\n"
        "1. Visit Summary\n"
        "2. Patient Condition\n"
        "3. Vital Signs\n"
        "4. Care Task Outcomes\n"
        "5. Medication Support\n"
        "6. Wellbeing and Observations\n"
        "7. Follow-up Required\n"
        "8. Overall Outcome\n\n"
        f"Patient context:\n{json.dumps(req.patientContext.model_dump(exclude_none=True), indent=2)}\n\n"
        f"Worker context:\n{json.dumps(req.workerContext.model_dump(exclude_none=True), indent=2)}\n\n"
        f"Visit context:\n{json.dumps(req.visitContext.model_dump(exclude_none=True), indent=2)}\n\n"
        f"Care tasks:\n{json.dumps([task.model_dump(exclude_none=True) for task in req.taskContext], indent=2)}\n\n"
        f"Medication support record:\n{json.dumps(req.medicationSupportContext.model_dump(exclude_none=True) if req.medicationSupportContext else None, indent=2)}\n\n"
        f"Events:\n{json.dumps([event.model_dump(exclude_none=True) for event in (req.eventContext or [])], indent=2)}\n\n"
        f"Risk alerts:\n{json.dumps([risk.model_dump(exclude_none=True) for risk in (req.riskContext or [])], indent=2)}\n\n"
        f"Completed Finish Visit care outcome form:\n{json.dumps(req.careOutcomeForm, indent=2)}"
    )


def _visit_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VisitRepositoryUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, VisitNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, VisitAccessError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, VisitValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, psycopg.errors.InvalidTextRepresentation):
        logger.warning("Visit identifier rejected: %s", exc)
        return HTTPException(status_code=400, detail="Invalid visit or task identifier format")
    logger.exception("Visit repository operation failed")
    return HTTPException(status_code=500, detail="Visit workflow database operation failed")


def _training_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TrainingRepositoryUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, TrainingTopicNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, psycopg.errors.InvalidTextRepresentation):
        logger.warning("Training topic identifier rejected: %s", exc)
        return HTTPException(status_code=400, detail="Invalid training topic identifier format")
    logger.exception("Training repository operation failed")
    return HTTPException(status_code=500, detail="Training material database operation failed")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "c3a-core-api",
        "ai": await ai_client.health(),
        "database": await database_health_checker.health(),
    }


@app.get("/training/topics", response_model=TrainingTopicsResponse)
def list_training_topics():
    try:
        return TrainingTopicsResponse(topics=training_repository.list_topics())
    except Exception as exc:
        raise _training_error(exc) from exc


@app.get("/training/topics/{topic_id}/materials", response_model=TrainingMaterialsResponse)
def list_training_materials(topic_id: str):
    try:
        return TrainingMaterialsResponse.model_validate(
            training_repository.list_materials(topic_id)
        )
    except Exception as exc:
        raise _training_error(exc) from exc


@app.get("/training/materials/search", response_model=TrainingSearchResponse)
def search_training_materials(q: str = ""):
    try:
        return TrainingSearchResponse(results=training_repository.search_materials(q))
    except Exception as exc:
        raise _training_error(exc) from exc


@app.post("/training/task-materials", response_model=TaskMaterialsResponse)
async def task_materials(req: TaskMaterialsRequest, request: Request):
    try:
        return await ai_client.task_materials(
            req,
            request_id=getattr(request.state, "request_id", None),
        )
    except AiServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc


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
def get_visit(
    visit_id: str,
    workerId: str,
    role: Literal["care_worker", "nurse", "supervisor"],
):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.get_scenario(visit_id, workerId, role)
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.patch("/patients/{patient_id}/profile", response_model=ScenarioResponse)
def update_patient_profile(patient_id: str, req: UpdatePatientProfileRequest):
    try:
        payload = req.model_dump(exclude_unset=True)
        if req.name is not None:
            payload["displayName"] = req.name
        return ScenarioResponse.model_validate(
            visit_repository.update_patient_profile(
                patient_id, payload, req.visitId, req.workerId, req.role
            )
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
def complete_task(visit_id: str, task_id: str, req: Optional[TaskStatusRequest] = None):
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
            visit_repository.update_task_status(visit_id, task_id, req.status, req.workerId, **({"note": req.note} if req.note is not None else {}))
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/tasks/{task_id}/issue", response_model=ScenarioResponse)
def report_task_issue(visit_id: str, task_id: str, req: TaskIssueRequest):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.report_task_issue(visit_id, task_id, req.type, req.workerId, **({"note": req.note} if req.note is not None else {}))
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.patch("/visits/{visit_id}/medication-support", response_model=ScenarioResponse)
def update_medication_support(visit_id: str, req: MedicationSupportRequest):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.update_medication_support(visit_id, req.model_dump(exclude_none=True))
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.patch("/visits/{visit_id}/alerts/{alert_id}", response_model=ScenarioResponse)
def transition_visit_alert(visit_id: str, alert_id: str, req: AlertActionRequest):
    try:
        return ScenarioResponse.model_validate(
            visit_repository.transition_alert(
                visit_id,
                alert_id,
                req.action,
                req.workerId,
                req.role,
                req.note,
            )
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/complete", response_model=ScenarioResponse)
def complete_visit(visit_id: str, req: CompleteVisitRequest):
    try:
        snapshot = req.checkOut.model_dump(exclude_none=True) if req.checkOut else None
        return ScenarioResponse.model_validate(
            visit_repository.complete_visit(visit_id, req.workerId, snapshot, **({"report": req.report} if req.report is not None else {}))
        )
    except Exception as exc:
        raise _visit_error(exc) from exc


@app.post("/visits/{visit_id}/report", response_model=GenerateVisitReportResponse)
async def generate_visit_report(visit_id: str, req: GenerateVisitReportRequest, request: Request):
    started_at = time.perf_counter()
    logger.info("API POST /visits/%s/report received", visit_id)
    prompt = _visit_report_prompt(req)
    try:
        ai_response = await ai_client.chat(
            ChatRequest(
                messages=[
                    {
                        "role": "system",
                        "content": "You generate concise, accurate aged-care visit reports from structured HCW forms.",
                    },
                    {"role": "user", "content": prompt},
                ],
                patientContext=req.patientContext,
                workerContext=req.workerContext,
                visitContext=req.visitContext,
                taskContext=req.taskContext,
                eventContext=req.eventContext,
                riskContext=req.riskContext,
                responseWordLimit=0,
            ),
            request_id=getattr(request.state, "request_id", None),
        )
        logger.info(
            "API POST /visits/%s/report completed elapsed_ms=%.1f chars=%s",
            visit_id,
            (time.perf_counter() - started_at) * 1000,
            len(ai_response.reply),
        )
        return GenerateVisitReportResponse(report=ai_response.reply)
    except AiServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc


@app.get("/patients/{patient_id}/summary", response_model=PatientSummaryResponse)
async def patient_summary(patient_id: str, request: Request):
    started_at = time.perf_counter()
    logger.info("API GET /patients/%s/summary received", patient_id)
    try:
        payload = await ai_client.patient_summary(
            patient_id,
            request_id=getattr(request.state, "request_id", None),
        )
    except AiServiceUnavailable as exc:
        if "no_patient_records" in str(exc):
            raise HTTPException(status_code=404, detail="No database records found for this patient") from exc
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc
    logger.info(
        "API GET /patients/%s/summary completed elapsed_ms=%.1f chars=%s",
        patient_id,
        (time.perf_counter() - started_at) * 1000,
        len(payload.get("summary", "")),
    )
    return PatientSummaryResponse(
        summary=payload.get("summary", ""),
        patientId=patient_id,
        records=payload.get("records", []),
    )


@app.post("/ai/risk/analyse", response_model=RiskAnalysisResponse)
async def analyse_risk(req: RiskAnalysisRequest, request: Request):
    try:
        return await ai_client.analyse_risk(
            req,
            request_id=getattr(request.state, "request_id", None),
        )
    except AiServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc


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
        return ChatResponse(
            reply=ai_response.reply,
            sources=ai_response.sources,
            sourceReferences=ai_response.sourceReferences,
        )
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


@app.post("/translate", response_model=TranslationResponse)
async def translate(req: TranslationRequest, request: Request):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text to translate must not be empty")
    if not req.targetLanguage.strip():
        raise HTTPException(status_code=400, detail="Target language must not be empty")

    started_at = time.perf_counter()
    logger.info(
        "API POST /translate received target_language=%s text_preview=%r",
        req.targetLanguage,
        _preview(req.text),
    )
    try:
        ai_response = await ai_client.translate(
            req,
            request_id=getattr(request.state, "request_id", None),
        )
        logger.info(
            "API POST /translate completed elapsed_ms=%.1f source_language=%s translated_chars=%s",
            (time.perf_counter() - started_at) * 1000,
            ai_response.sourceLanguage,
            len(ai_response.translatedText),
        )
        return TranslationResponse.model_validate(ai_response.model_dump())
    except AiServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail="AI service is unavailable") from exc


@app.post("/speech/transcribe", response_model=SpeechTranscriptionResponse)
async def transcribe_speech(
    request: Request,
    audio: UploadFile = File(...),
    sourceLanguage: str = Form(...),
    speakerRole: Literal["care_worker", "patient"] = Form(...),
    visitId: str | None = Form(None),
    clientRequestId: str | None = Form(None),
):
    max_bytes = int(os.getenv("SPEECH_MAX_UPLOAD_BYTES", "10485760"))
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Audio file is required")
    data = await audio.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Audio recording must not be empty")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio recording exceeds the upload limit")
    request_id = clientRequestId or getattr(request.state, "request_id", None) or str(uuid.uuid4())
    try:
        result = await ai_client.transcribe_speech(data, audio.filename or "recording.m4a", content_type, sourceLanguage, speakerRole, request_id)
    except AiServiceUnavailable as exc:
        logger.warning("Speech transcription unavailable request_id=%s visit_id=%s error=%s", request_id, visitId, exc)
        raise HTTPException(status_code=502, detail="Speech recognition service is unavailable") from exc
    logger.info("Speech transcription complete request_id=%s visit_id=%s language=%s role=%s transcript_chars=%s", request_id, visitId, sourceLanguage, speakerRole, len(result.transcript))
    return result


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
