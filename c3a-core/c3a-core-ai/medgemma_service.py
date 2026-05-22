"""
MedGemma model wrapper.

Supports:
  - Text-only conversations
  - Multimodal input (image + text) via MedGemma-4B-IT or 27B-IT
  - Patient context injection as a system prompt

Model IDs (Hugging Face):
  google/medgemma-4b-it    <- recommended for most deployments
  google/medgemma-27b-it   <- higher accuracy, needs more VRAM
"""

import asyncio
import base64
import io
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Lazy imports so the server starts even without GPU/model.
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    from PIL import Image

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("transformers/torch not installed - running in DEMO mode.")


SYSTEM_PROMPT = """You are MedGemma, an AI medical assistant.
You assist clinicians by answering medical questions, interpreting imaging,
summarising patient notes, and providing evidence-based clinical guidance.
When retrieved clinical evidence or PostgreSQL patient context is provided,
use it as the primary source for your answer and do not ignore it.
For care-worker questions, answer with practical aged-care actions and
escalation/red-flag advice where appropriate.
When visit workflow context is provided, tailor the answer to the current
visit status, task list, recent events, active risks, patient mobility, CALD
needs, and the health worker's role. Explain what the care worker should do
next in the real workflow, not only generic clinical facts.
Treat location data as visit workflow context only. If a location check is
outside the expected area, advise address confirmation and documentation; do
not accuse the worker or make surveillance conclusions.
Always remind the user that AI advice does not replace professional clinical judgment.
Be concise, accurate, and compassionate."""


def _build_patient_context(patient) -> str:
    if not patient:
        return ""
    parts = ["## Linked Patient"]
    if patient.name:
        parts.append(f"- Name: {patient.name}")
    if patient.age:
        parts.append(f"- Age: {patient.age}")
    if patient.gender:
        parts.append(f"- Gender: {patient.gender}")
    if patient.medicalRecordNumber:
        parts.append(f"- MRN: {patient.medicalRecordNumber}")
    if patient.diagnosis:
        parts.append(f"- Diagnosis: {patient.diagnosis}")
    if patient.notes:
        parts.append(f"- Notes: {patient.notes}")
    if getattr(patient, "preferredLanguage", None):
        parts.append(f"- Preferred language: {patient.preferredLanguage}")
    if getattr(patient, "interpreterRequired", None) is not None:
        parts.append(f"- Interpreter required: {patient.interpreterRequired}")
    if getattr(patient, "culturalBackground", None):
        parts.append(f"- Cultural background: {patient.culturalBackground}")
    if getattr(patient, "mobilitySupport", None):
        parts.append(f"- Mobility support: {patient.mobilitySupport}")
    if getattr(patient, "cognitiveStatus", None):
        parts.append(f"- Cognitive status: {patient.cognitiveStatus}")
    if getattr(patient, "dietaryNotes", None):
        parts.append(f"- Dietary notes: {patient.dietaryNotes}")
    if getattr(patient, "communicationNotes", None):
        parts.append(f"- Communication notes: {patient.communicationNotes}")
    if getattr(patient, "careRiskFlags", None):
        parts.append(f"- Care risk flags: {', '.join(patient.careRiskFlags)}")
    if getattr(patient, "allergies", None):
        parts.append(f"- Allergies: {', '.join(patient.allergies)}")
    if getattr(patient, "medications", None):
        parts.append(f"- Medications: {', '.join(patient.medications)}")
    return "\n".join(parts)


def _build_workflow_context(worker=None, visit=None, tasks=None, events=None, risks=None) -> str:
    parts: list[str] = []
    if worker:
        parts.append("## Current Health Worker")
        if getattr(worker, "name", None):
            parts.append(f"- Name: {worker.name}")
        if getattr(worker, "role", None):
            parts.append(f"- Role: {worker.role}")
        if getattr(worker, "shift", None):
            parts.append(f"- Shift: {worker.shift}")
    if visit:
        parts.append("## Current Visit")
        for label, attr in [
            ("Visit ID", "id"),
            ("Scheduled at", "scheduledAt"),
            ("Arrived at", "arrivedAt"),
            ("Location/purpose", "location"),
            ("Status", "status"),
        ]:
            value = getattr(visit, attr, None)
            if value:
                parts.append(f"- {label}: {value}")
        if getattr(visit, "plannedAddress", None):
            parts.append(f"- Planned address: {visit.plannedAddress}")
        threshold = getattr(visit, "locationThresholdMeters", None)
        if threshold:
            parts.append(f"- Location threshold: {threshold} metres")
        for label, attr in [("Check-in", "checkIn"), ("Check-out", "checkOut")]:
            snapshot = getattr(visit, attr, None)
            if snapshot:
                line = f"- {label}: {getattr(snapshot, 'source', 'unknown')} at {getattr(snapshot, 'timestamp', 'unknown time')}"
                distance = getattr(snapshot, "distanceFromPlannedMeters", None)
                if distance is not None:
                    line += f"; {round(distance)} metres from planned location"
                accuracy = getattr(snapshot, "accuracyMeters", None)
                if accuracy is not None:
                    line += f"; GPS accuracy {round(accuracy)} metres"
                within = getattr(snapshot, "withinExpectedArea", None)
                if within is not None:
                    line += f"; within expected area: {within}"
                note = getattr(snapshot, "note", None)
                if note:
                    line += f"; note: {note}"
                parts.append(line)
    if tasks:
        parts.append("## Current Care Tasks")
        for task in tasks[:12]:
            label = getattr(task, "label", None) or getattr(task, "id", "Task")
            status = getattr(task, "status", "unknown")
            due_at = getattr(task, "dueAt", None)
            detail = getattr(task, "detail", None)
            line = f"- {label}: {status}"
            if due_at:
                line += f" (due {due_at})"
            if detail:
                line += f"; {detail}"
            parts.append(line)
    if events:
        parts.append("## Recent Real-World Events")
        for event in events[:8]:
            event_type = getattr(event, "type", "event")
            event_time = getattr(event, "timestamp", "")
            note = getattr(event, "note", None)
            line = f"- {event_type}"
            if event_time:
                line += f" at {event_time}"
            if note:
                line += f": {note}"
            parts.append(line)
    if risks:
        parts.append("## Active Risk Alerts")
        for risk in risks[:8]:
            title = getattr(risk, "title", None) or getattr(risk, "id", "Risk")
            level = getattr(risk, "level", "unknown")
            message = getattr(risk, "message", "")
            parts.append(f"- {level.upper()}: {title}. {message}")
    if not parts:
        return ""
    return "\n".join(parts)


def _build_rag_context(rag_context) -> str:
    if not rag_context:
        return ""
    if isinstance(rag_context, str):
        return rag_context.strip()
    return str(rag_context).strip()


class MedGemmaService:
    model_name: str = "google/medgemma-4b-it"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.provider = os.getenv("MEDGEMMA_PROVIDER", "local").strip().lower()
        self.remote_url = _normalise_remote_url(os.getenv("MEDGEMMA_REMOTE_URL", ""))
        self.remote_api_token = os.getenv("MEDGEMMA_REMOTE_API_TOKEN", "").strip()
        self.remote_timeout_seconds = float(
            os.getenv("MEDGEMMA_REMOTE_TIMEOUT_SECONDS", "300")
        )
        self._pipe = None
        self._loaded = False
        self._load_error = None
        if not self.enabled:
            logger.info("AI model loading is disabled by configuration.")
        elif self.provider == "remote":
            if self.remote_url:
                logger.info("Using remote MedGemma provider at %s", self.remote_url)
                self._loaded = True
            else:
                self._load_error = "MEDGEMMA_REMOTE_URL is not configured"
                logger.error("Remote MedGemma provider selected but URL is missing.")
        elif HAS_TRANSFORMERS:
            self._load_model()
        else:
            logger.info("Running in DEMO mode - model not loaded.")

    def _load_model(self):
        """Load model once on startup. Change model_name for 27B."""
        try:
            logger.info("Loading %s ...", self.model_name)
            self._pipe = pipeline(
                "text-generation",
                model=self.model_name,
                torch_dtype="auto",
                device_map="auto",
            )
            self._loaded = True
            self._load_error = None
            logger.info("Model loaded successfully")
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            self._loaded = False
            self._load_error = str(exc)

    def status(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "enabled": self.enabled,
            "provider": self.provider,
            "loaded": self._loaded,
            "task": "remote-http" if self.provider == "remote" else "text-generation",
            "remote_url_configured": bool(self.remote_url),
            "remote_auth_configured": bool(self.remote_api_token),
            "remote_timeout_seconds": self.remote_timeout_seconds,
            "load_error": self._load_error,
        }

    async def generate_reply(
        self,
        messages: list[tuple[str, str]],
        patient=None,
        worker=None,
        visit=None,
        tasks=None,
        events=None,
        risks=None,
        attachments=None,
        rag_context=None,
    ) -> str:
        """
        Async wrapper - runs the blocking inference in a thread pool.
        """
        if not self._loaded:
            return self._demo_reply(messages, rag_context)

        if self.provider == "remote":
            return await self._remote_generate(
                messages,
                patient,
                attachments or [],
                rag_context,
                worker=worker,
                visit=visit,
                tasks=tasks or [],
                events=events or [],
                risks=risks or [],
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_generate,
            messages,
            patient,
            worker,
            visit,
            tasks or [],
            events or [],
            risks or [],
            attachments or [],
            rag_context,
        )

    def _sync_generate(
        self,
        messages,
        patient,
        worker,
        visit,
        tasks,
        events,
        risks,
        attachments,
        rag_context=None,
    ) -> str:
        system_parts = [SYSTEM_PROMPT]
        patient_ctx = _build_patient_context(patient)
        if patient_ctx:
            system_parts.append(patient_ctx)
        workflow_ctx = _build_workflow_context(worker, visit, tasks, events, risks)
        if workflow_ctx:
            system_parts.append(workflow_ctx)
        rag_ctx = _build_rag_context(rag_context)
        if rag_ctx:
            system_parts.append(rag_ctx)

        hf_messages = [
            {"role": "system", "content": "\n\n".join(system_parts)}]

        for role, content in messages:
            if role == "user" and attachments and _has_image(attachments):
                img_content = _decode_first_image(attachments)
                if img_content:
                    hf_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "image", "image": img_content},
                                {"type": "text", "text": content},
                            ],
                        }
                    )
                    attachments = []
                    continue
            hf_messages.append({"role": role, "content": content})

        output = self._pipe(
            hf_messages,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
        )
        generated = output[0]["generated_text"]
        if isinstance(generated, list):
            return generated[-1].get("content", "").strip()
        return str(generated).strip()

    async def _remote_generate(
        self,
        messages,
        patient,
        attachments,
        rag_context=None,
        worker=None,
        visit=None,
        tasks=None,
        events=None,
        risks=None,
    ) -> str:
        remote_messages = _build_remote_messages(
            messages,
            patient,
            rag_context,
            worker=worker,
            visit=visit,
            tasks=tasks or [],
            events=events or [],
            risks=risks or [],
        )
        rag_ctx = _build_rag_context(rag_context)
        payload = {
            "messages": remote_messages,
            "patientContext": _serialise_model(patient),
            "workerContext": _serialise_model(worker),
            "visitContext": _serialise_model(visit),
            "taskContext": [_serialise_model(item) for item in tasks or []],
            "eventContext": [_serialise_model(item) for item in events or []],
            "riskContext": [_serialise_model(item) for item in risks or []],
            "attachments": [_serialise_model(item) for item in attachments],
            "ragContext": rag_ctx,
            "context": rag_ctx,
            "max_new_tokens": int(os.getenv("MEDGEMMA_REMOTE_MAX_NEW_TOKENS", "384")),
            "temperature": float(os.getenv("MEDGEMMA_REMOTE_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("MEDGEMMA_REMOTE_TOP_P", "0.9")),
        }
        headers = {}
        if self.remote_api_token:
            headers["Authorization"] = f"Bearer {self.remote_api_token}"

        try:
            async with httpx.AsyncClient(timeout=self.remote_timeout_seconds) as client:
                response = await client.post(
                    self.remote_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error(
                "Remote MedGemma returned HTTP %s: %s",
                exc.response.status_code,
                detail,
            )
            return (
                "[Remote MedGemma error]\n\n"
                f"Colab returned HTTP {exc.response.status_code}: {detail}"
            )
        except Exception as exc:
            logger.error("Remote MedGemma request failed: %s", exc, exc_info=True)
            return (
                "[Remote MedGemma unavailable]\n\n"
                "The local AI service could not reach the Colab MedGemma endpoint. "
                f"Error: {exc}"
            )

        reply = data.get("reply")
        if isinstance(reply, str) and reply.strip():
            if _looks_like_missing_context(reply) and _has_postgres_context(rag_ctx):
                logger.warning(
                    "Remote MedGemma ignored PostgreSQL context; returning local context fallback."
                )
                return _context_fallback_reply(messages, rag_ctx)
            return reply.strip()
        return str(data).strip()

    # Demo mode (no GPU).
    def _demo_reply(self, messages: list[tuple[str, str]], rag_context=None) -> str:
        last_user = next(
            (content for role, content in reversed(messages) if role == "user"), ""
        )
        context_preview = _demo_context_preview(rag_context)
        if not self.enabled:
            if context_preview:
                return (
                    "[AI disabled]\n\n"
                    f"You asked: \"{last_user[:120]}\"\n\n"
                    "The retrieved context that would be sent to MedGemma is:\n\n"
                    f"{context_preview}\n\n"
                    "Set C3A_AI_ENABLED=true in c3a-core-ai/.env and restart the AI service "
                    "to enable model inference."
                )
            return (
                "[AI disabled]\n\n"
                f"You asked: \"{last_user[:120]}\"\n\n"
                "Local MedGemma model loading is disabled by configuration. "
                "Set C3A_AI_ENABLED=true in c3a-core-ai/.env and restart the AI service "
                "to enable model inference."
            )
        if context_preview:
            return (
                "[DEMO - MedGemma not loaded]\n\n"
                f"You asked: \"{last_user[:120]}\"\n\n"
                "The retrieved context that would be sent to MedGemma is:\n\n"
                f"{context_preview}\n\n"
                "Please ensure the model is downloaded and GPU/CPU resources are available."
            )
        return (
            "[DEMO - MedGemma not loaded]\n\n"
            f"You asked: \"{last_user[:120]}\"\n\n"
            "In production, MedGemma would provide a clinical response here. "
            "Please ensure the model is downloaded and GPU/CPU resources are available."
        )


def _has_image(attachments) -> bool:
    return any(getattr(attachment, "mimeType", "").startswith("image/") for attachment in attachments)


def _decode_first_image(attachments):
    for attachment in attachments:
        if getattr(attachment, "mimeType", "").startswith("image/"):
            try:
                data = base64.b64decode(attachment.base64)
                return Image.open(io.BytesIO(data)).convert("RGB")
            except Exception as exc:
                logger.warning("Image decode failed: %s", exc)
    return None


def _normalise_remote_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/generate"):
        return url
    return f"{url}/generate"


def _build_remote_messages(
    messages,
    patient,
    rag_context=None,
    worker=None,
    visit=None,
    tasks=None,
    events=None,
    risks=None,
) -> list[dict[str, str]]:
    system_parts = [SYSTEM_PROMPT]
    patient_ctx = _build_patient_context(patient)
    if patient_ctx:
        system_parts.append(patient_ctx)
    workflow_ctx = _build_workflow_context(worker, visit, tasks or [], events or [], risks or [])
    if workflow_ctx:
        system_parts.append(workflow_ctx)
    rag_ctx = _build_rag_context(rag_context)
    if rag_ctx:
        system_parts.append(rag_ctx)

    remote_messages = [{"role": "system", "content": "\n\n".join(system_parts)}]
    rag_ctx = _build_rag_context(rag_context)
    for role, content in messages:
        if role == "user" and rag_ctx:
            content = (
                "Use the retrieved context below to answer the question. "
                "The retrieved context is available to you and must be used as the primary evidence. "
                "If PostgreSQL synthetic patient context is present, treat it as available data and do not say you lack access. "
                "If clinical evidence sources are present, cite them in the answer as [Source 1], [Source 2], etc. "
                "Answer only from the retrieved context when patient-specific records are requested.\n\n"
                f"{rag_ctx}\n\n"
                f"Question: {content}"
            )
        remote_messages.append({"role": role, "content": content})
    return remote_messages


def _serialise_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    return value


def _demo_context_preview(rag_context) -> str:
    context = _build_rag_context(rag_context)
    if not context:
        return ""
    if len(context) <= 1800:
        return context
    return f"{context[:1800].rstrip()}..."


def _has_postgres_context(rag_context: str) -> bool:
    return "## Retrieved PostgreSQL Synthetic Patient Context" in rag_context


def _looks_like_missing_context(reply: str) -> bool:
    lowered = reply.lower()
    missing_access_phrases = [
        "do not have access",
        "don't have access",
        "no access",
        "cannot access",
        "can't access",
        "not have access",
        "do not have the patient's",
        "don't have the patient's",
    ]
    return any(phrase in lowered for phrase in missing_access_phrases)


def _context_fallback_reply(messages: list[tuple[str, str]], rag_context: str) -> str:
    postgres_context = _postgres_context_only(rag_context)
    if not postgres_context:
        postgres_context = rag_context
    context_preview = postgres_context if len(postgres_context) <= 2200 else f"{postgres_context[:2200].rstrip()}..."
    last_user = next(
        (content for role, content in reversed(messages) if role == "user"), ""
    )
    return (
        "The remote model did not use the retrieved PostgreSQL patient context, "
        "so here is the relevant synthetic database context retrieved for your question.\n\n"
        f"Question: {last_user}\n\n"
        f"{context_preview}"
    )


def _postgres_context_only(rag_context: str) -> str:
    marker = "## Retrieved PostgreSQL Synthetic Patient Context"
    if marker not in rag_context:
        return ""
    start = rag_context.index(marker)
    next_section = rag_context.find("\n\n## Retrieved Clinical Evidence", start + len(marker))
    if next_section == -1:
        return rag_context[start:].strip()
    return rag_context[start:next_section].strip()
