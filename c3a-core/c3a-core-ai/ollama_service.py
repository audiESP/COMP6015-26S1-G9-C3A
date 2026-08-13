"""Ollama-backed inference for the C3A Core AI service."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator

import httpx


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the clinical context-aware assistant for C3A Core.
Use supplied patient, visit, task, risk, database, and retrieved evidence context
as the primary source of truth when it is present. For general questions with
no supplied context, answer from general knowledge and state relevant limits.
Never invent patient records, medications,
allergies, observations, source citations, or completed care tasks.
When clinical evidence sources are supplied, cite them using the provided
[Source N] labels only. Clearly distinguish facts in the supplied context from
general clinical guidance and information that is missing or uncertain.
For care-worker questions, give practical aged-care actions and escalation or
red-flag advice appropriate to the worker's role. Tailor guidance to the current
visit status, task list, recent events, active risks, patient mobility, CALD
needs, and the health worker's role.
Treat location data as visit workflow context only. If a location check is
outside the expected area, advise address confirmation and documentation; do
not accuse the worker or make surveillance conclusions.
Do not diagnose or replace professional clinical judgment. Be concise,
accurate, and compassionate."""


class OllamaServiceError(RuntimeError):
    """Raised when Ollama cannot provide a valid model response."""


class UnsupportedAttachmentError(OllamaServiceError):
    """Raised when attachments are supplied to a text-only model."""


class OllamaService:
    def __init__(
        self,
        enabled: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.enabled = enabled
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model_name = os.getenv("OLLAMA_MODEL", "llama3:latest").strip()
        self.timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "10m").strip()
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "192"))
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
        self.top_p = float(os.getenv("OLLAMA_TOP_P", "0.9"))
        self.max_context_chars = int(os.getenv("OLLAMA_MAX_CONTEXT_CHARS", "12000"))
        self._transport = transport
        self._loaded = False
        self._load_error = None if enabled else "AI model inference is disabled"
        self._supports_images = False

    def status(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "enabled": self.enabled,
            "provider": "ollama",
            "loaded": self._loaded,
            "task": "chat",
            "base_url": self.base_url,
            "context_length": self.num_ctx,
            "supports_images": self._supports_images,
            "device": "ollama-managed",
            "timeout_seconds": self.timeout_seconds,
            "load_error": self._load_error,
        }

    async def check_health(self) -> dict[str, Any]:
        if not self.enabled:
            self._loaded = False
            self._load_error = "AI model inference is disabled"
            return self.status()

        try:
            async with self._client(timeout=min(self.timeout_seconds, 10.0)) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                data = response.json()
            model = next(
                (
                    item
                    for item in data.get("models", [])
                    if item.get("name") == self.model_name
                    or item.get("model") == self.model_name
                ),
                None,
            )
            if model is None:
                raise OllamaServiceError(
                    f"Ollama model '{self.model_name}' is not installed"
                )
            capabilities = model.get("capabilities", [])
            self._supports_images = "vision" in capabilities
            self._loaded = True
            self._load_error = None
        except Exception as exc:
            self._loaded = False
            self._load_error = str(exc)
            logger.warning("Ollama health check failed: %s", exc)
        return self.status()

    async def generate_reply(
        self,
        messages: list[tuple[str, str]],
        patient=None,
        worker=None,
        visit=None,
        tasks=None,
        events=None,
        risks=None,
        checklist=None,
        attachments=None,
        rag_context=None,
    ) -> str:
        parts = [
            chunk
            async for chunk in self.stream_reply(
                messages=messages,
                patient=patient,
                worker=worker,
                visit=visit,
                tasks=tasks,
                events=events,
                risks=risks,
                checklist=checklist,
                attachments=attachments,
                rag_context=rag_context,
            )
        ]
        reply = "".join(parts).strip()
        if not reply:
            self._load_error = "Ollama returned a response without message content"
            raise OllamaServiceError(self._load_error)
        return reply

    async def stream_reply(
        self,
        messages: list[tuple[str, str]],
        patient=None,
        worker=None,
        visit=None,
        tasks=None,
        events=None,
        risks=None,
        checklist=None,
        attachments=None,
        rag_context=None,
    ) -> AsyncIterator[str]:
        if not self.enabled:
            raise OllamaServiceError("AI model inference is disabled")
        if attachments:
            raise UnsupportedAttachmentError(
                "The configured local Llama model does not support attachments"
            )
        if not self._loaded:
            await self.check_health()
        if not self._loaded:
            raise OllamaServiceError(self._load_error or "Ollama model is unavailable")

        ollama_messages = _build_ollama_messages(
            messages=messages,
            patient=patient,
            worker=worker,
            visit=visit,
            tasks=tasks or [],
            events=events or [],
            risks=risks or [],
            checklist=checklist or [],
            rag_context=rag_context,
            max_context_chars=self.max_context_chars,
        )
        payload = {
            "model": self.model_name,
            "messages": ollama_messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }
        logger.info(
            "Ollama generation started model=%s system_chars=%s conversation_messages=%s patient_context=%s num_ctx=%s num_predict=%s stream=True",
            self.model_name,
            len(ollama_messages[0]["content"]),
            len(ollama_messages) - 1,
            patient is not None,
            self.num_ctx,
            self.num_predict,
        )
        generation_started_at = time.perf_counter()

        try:
            async with self._client() as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for chunk in _stream_response_chunks(response, generation_started_at):
                        yield chunk
        except httpx.HTTPStatusError as exc:
            self._load_error = f"Ollama returned HTTP {exc.response.status_code}"
            logger.error(self._load_error)
            raise OllamaServiceError(self._load_error) from exc
        except (httpx.RequestError, ValueError) as exc:
            self._loaded = False
            self._load_error = f"Unable to call Ollama: {exc}"
            logger.error(self._load_error)
            raise OllamaServiceError(self._load_error) from exc

        self._loaded = True
        self._load_error = None

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds if timeout is None else timeout,
            transport=self._transport,
        )


def _build_ollama_messages(
    messages,
    patient=None,
    worker=None,
    visit=None,
    tasks=None,
    events=None,
    risks=None,
    checklist=None,
    rag_context=None,
    max_context_chars=12000,
) -> list[dict[str, str]]:
    context_parts = [SYSTEM_PROMPT, "Keep the answer concise. Do not repeat the question. Use short paragraphs or bullet points."]
    patient_context = _build_patient_context(patient)
    if patient_context:
        context_parts.append(patient_context)
    workflow_context = _build_workflow_context(
        worker, visit, tasks or [], events or [], risks or [], checklist or []
    )
    if workflow_context:
        context_parts.append(workflow_context)
    retrieved_context = _build_rag_context(rag_context)
    if retrieved_context:
        context_parts.append(retrieved_context)

    conversation = [
        {"role": role, "content": content}
        for role, content in messages
        if role in {"user", "assistant"} and isinstance(content, str)
    ]
    conversation_chars = sum(len(item["content"]) for item in conversation)
    system_budget = max(4000, max_context_chars - conversation_chars)
    system_content = "\n\n".join(context_parts)
    if len(system_content) > system_budget:
        system_content = system_content[:system_budget].rstrip() + "\n\n[Context truncated]"
    return [{"role": "system", "content": system_content}, *conversation]


def _build_patient_context(patient) -> str:
    if not patient:
        return ""
    parts = ["## Linked Patient"]
    fields = [
        ("Name", "name"),
        ("Age", "age"),
        ("Gender", "gender"),
        ("MRN", "medicalRecordNumber"),
        ("Diagnosis", "diagnosis"),
        ("Notes", "notes"),
        ("Preferred language", "preferredLanguage"),
        ("Interpreter required", "interpreterRequired"),
        ("Cultural background", "culturalBackground"),
        ("Mobility support", "mobilitySupport"),
        ("Cognitive status", "cognitiveStatus"),
        ("Dietary notes", "dietaryNotes"),
        ("Communication notes", "communicationNotes"),
    ]
    for label, attribute in fields:
        value = getattr(patient, attribute, None)
        if value is not None and value != "":
            parts.append(f"- {label}: {value}")
    for label, attribute in [
        ("Care risk flags", "careRiskFlags"),
        ("Allergies", "allergies"),
        ("Medications", "medications"),
    ]:
        value = getattr(patient, attribute, None)
        if value:
            parts.append(f"- {label}: {', '.join(value)}")
    return "\n".join(parts)


def _build_workflow_context(worker=None, visit=None, tasks=None, events=None, risks=None, checklist=None) -> str:
    parts: list[str] = []
    if worker:
        parts.append("## Current Health Worker")
        for label, attribute in [("Name", "name"), ("Role", "role"), ("Shift", "shift")]:
            value = getattr(worker, attribute, None)
            if value:
                parts.append(f"- {label}: {value}")
    if visit:
        parts.append("## Current Visit")
        for label, attribute in [
            ("Visit ID", "id"),
            ("Scheduled at", "scheduledAt"),
            ("Arrived at", "arrivedAt"),
            ("Location/purpose", "location"),
            ("Status", "status"),
            ("Planned address", "plannedAddress"),
        ]:
            value = getattr(visit, attribute, None)
            if value:
                parts.append(f"- {label}: {value}")
        threshold = getattr(visit, "locationThresholdMeters", None)
        if threshold:
            parts.append(f"- Location threshold: {threshold} metres")
        for label, attribute in [("Check-in", "checkIn"), ("Check-out", "checkOut")]:
            snapshot = getattr(visit, attribute, None)
            if snapshot:
                line = (
                    f"- {label}: {getattr(snapshot, 'source', 'unknown')} at "
                    f"{getattr(snapshot, 'timestamp', 'unknown time')}"
                )
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
            line = f"- {label}: {getattr(task, 'status', 'unknown')}"
            due_at = getattr(task, "dueAt", None)
            if due_at:
                line += f" (due {due_at})"
            detail = getattr(task, "detail", None)
            if detail:
                line += f"; {detail}"
            parts.append(line)
    if checklist:
        parts.append("## Incident Checklist")
        for item in checklist[:12]:
            label = getattr(item, "label", None) or getattr(item, "id", "Checklist item")
            completed = getattr(item, "completed", False)
            status = "complete" if completed else "incomplete"
            parts.append(f"- {label}: {status}")
    if events:
        parts.append("## Recent Real-World Events")
        for event in events[:8]:
            line = f"- {getattr(event, 'type', 'event')}"
            event_time = getattr(event, "timestamp", "")
            if event_time:
                line += f" at {event_time}"
            note = getattr(event, "note", None)
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
    return "\n".join(parts)


def _build_rag_context(rag_context) -> str:
    if not rag_context:
        return ""
    if isinstance(rag_context, str):
        return rag_context.strip()
    return str(rag_context).strip()


async def _stream_response_chunks(
    response: httpx.Response,
    started_at: float | None = None,
) -> AsyncIterator[str]:
    """Convert Ollama's newline-delimited response into content chunks."""
    started_at = started_at or time.perf_counter()
    parts: list[str] = []
    first_token_ms: float | None = None
    final_data: dict[str, Any] = {}
    async for line in response.aiter_lines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if data.get("error"):
            raise OllamaServiceError(str(data["error"]))
        content = data.get("message", {}).get("content")
        if isinstance(content, str):
            if content and first_token_ms is None:
                first_token_ms = (time.perf_counter() - started_at) * 1000
            if content:
                parts.append(content)
                yield content
        if data.get("done"):
            final_data = data
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    eval_count = final_data.get("eval_count")
    eval_duration = final_data.get("eval_duration")
    tokens_per_second = None
    if isinstance(eval_count, int) and isinstance(eval_duration, int) and eval_duration > 0:
        tokens_per_second = eval_count / (eval_duration / 1_000_000_000)
    logger.info(
        "Ollama generation stream completed first_token_ms=%s elapsed_ms=%.1f prompt_tokens=%s output_tokens=%s output_chars=%s tokens_per_second=%s",
        f"{first_token_ms:.1f}" if first_token_ms is not None else "n/a",
        elapsed_ms,
        final_data.get("prompt_eval_count"),
        eval_count,
        sum(len(part) for part in parts),
        f"{tokens_per_second:.1f}" if tokens_per_second is not None else "n/a",
    )
