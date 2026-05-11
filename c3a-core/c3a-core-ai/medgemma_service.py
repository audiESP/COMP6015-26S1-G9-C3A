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
        attachments=None,
        rag_context=None,
    ) -> str:
        """
        Async wrapper - runs the blocking inference in a thread pool.
        """
        if not self._loaded:
            return self._demo_reply(messages, rag_context)

        if self.provider == "remote":
            return await self._remote_generate(messages, patient, attachments or [], rag_context)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_generate,
            messages,
            patient,
            attachments or [],
            rag_context,
        )

    def _sync_generate(self, messages, patient, attachments, rag_context=None) -> str:
        system_parts = [SYSTEM_PROMPT]
        patient_ctx = _build_patient_context(patient)
        if patient_ctx:
            system_parts.append(patient_ctx)
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

    async def _remote_generate(self, messages, patient, attachments, rag_context=None) -> str:
        remote_messages = _build_remote_messages(messages, patient, rag_context)
        rag_ctx = _build_rag_context(rag_context)
        payload = {
            "messages": remote_messages,
            "patientContext": _serialise_model(patient),
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


def _build_remote_messages(messages, patient, rag_context=None) -> list[dict[str, str]]:
    system_parts = [SYSTEM_PROMPT]
    patient_ctx = _build_patient_context(patient)
    if patient_ctx:
        system_parts.append(patient_ctx)
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
