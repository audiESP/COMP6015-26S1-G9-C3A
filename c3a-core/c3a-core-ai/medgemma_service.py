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
    ) -> str:
        """
        Async wrapper - runs the blocking inference in a thread pool.
        """
        if not self._loaded:
            return self._demo_reply(messages)

        if self.provider == "remote":
            return await self._remote_generate(messages, patient, attachments or [])

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_generate,
            messages,
            patient,
            attachments or [],
        )

    def _sync_generate(self, messages, patient, attachments) -> str:
        system_parts = [SYSTEM_PROMPT]
        patient_ctx = _build_patient_context(patient)
        if patient_ctx:
            system_parts.append(patient_ctx)

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

    async def _remote_generate(self, messages, patient, attachments) -> str:
        payload = {
            "messages": _build_remote_messages(messages, patient),
            "patientContext": _serialise_model(patient),
            "attachments": [_serialise_model(item) for item in attachments],
            "max_new_tokens": int(os.getenv("MEDGEMMA_REMOTE_MAX_NEW_TOKENS", "128")),
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
            return reply.strip()
        return str(data).strip()

    # Demo mode (no GPU).
    def _demo_reply(self, messages: list[tuple[str, str]]) -> str:
        last_user = next(
            (content for role, content in reversed(messages) if role == "user"), ""
        )
        if not self.enabled:
            return (
                "[AI disabled]\n\n"
                f"You asked: \"{last_user[:120]}\"\n\n"
                "Local MedGemma model loading is disabled by configuration. "
                "Set C3A_AI_ENABLED=true in c3a-core-ai/.env and restart the AI service "
                "to enable model inference."
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


def _build_remote_messages(messages, patient) -> list[dict[str, str]]:
    system_parts = [SYSTEM_PROMPT]
    patient_ctx = _build_patient_context(patient)
    if patient_ctx:
        system_parts.append(patient_ctx)

    remote_messages = [{"role": "system", "content": "\n\n".join(system_parts)}]
    remote_messages.extend({"role": role, "content": content} for role, content in messages)
    return remote_messages


def _serialise_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    return value
