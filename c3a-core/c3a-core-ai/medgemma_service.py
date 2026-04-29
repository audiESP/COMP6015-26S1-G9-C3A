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
from typing import Any

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

    def __init__(self):
        self._pipe = None
        self._loaded = False
        self._load_error = None
        if HAS_TRANSFORMERS:
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
            "loaded": self._loaded,
            "task": "text-generation",
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

    # Demo mode (no GPU).
    def _demo_reply(self, messages: list[tuple[str, str]]) -> str:
        last_user = next(
            (content for role, content in reversed(messages) if role == "user"), ""
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
