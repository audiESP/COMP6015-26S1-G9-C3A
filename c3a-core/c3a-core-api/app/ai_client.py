"""HTTP client for the C3A Core AI service."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator

import httpx

from .logging_utils import preview_object
from .schemas import (
    AiChatResponse,
    AiTranslationResponse,
    ChatRequest,
    RiskAnalysisRequest,
    RiskAnalysisResponse,
    TaskMaterialsRequest,
    TaskMaterialsResponse,
    TranslationRequest,
    SpeechTranscriptionResponse,
)


DEFAULT_AI_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_TIMEOUT_SECONDS = 300.0


class AiServiceUnavailable(Exception):
    """Raised when the AI service cannot be reached or returns an error."""


class AiClient:
    def __init__(self):
        self.base_url = os.getenv("C3A_AI_BASE_URL", DEFAULT_AI_BASE_URL).rstrip("/")
        self.timeout = float(os.getenv("C3A_AI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        self.logger = logging.getLogger(__name__)

    async def health(self) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/ai/health")
                response.raise_for_status()
                self.logger.info(
                    "AI client health completed base_url=%s status=%s elapsed_ms=%.1f",
                    self.base_url,
                    response.status_code,
                    (time.perf_counter() - started_at) * 1000,
                )
                return response.json()
        except Exception as exc:
            self.logger.warning(
                "AI client health failed base_url=%s elapsed_ms=%.1f error=%s",
                self.base_url,
                (time.perf_counter() - started_at) * 1000,
                exc,
                exc_info=True,
            )
            return {
                "status": "unavailable",
                "base_url": self.base_url,
                "error": str(exc),
            }

    async def chat(self, request: ChatRequest, request_id: str | None = None) -> AiChatResponse:
        started_at = time.perf_counter()
        self.logger.info(
            "AI client chat started base_url=%s request_id=%s timeout=%s latest_user_preview=%r",
            self.base_url,
            request_id,
            self.timeout,
            _latest_user_preview(request),
        )
        self.logger.debug(
            "AI client chat request request_id=%s payload=%s",
            request_id,
            preview_object(request.model_dump(exclude_none=True)),
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/chat",
                    json=request.model_dump(exclude_none=True),
                    headers=_request_headers(request_id),
                )
                response.raise_for_status()
                payload = response.json()
                self.logger.info(
                    "AI client chat completed request_id=%s status=%s elapsed_ms=%.1f",
                    request_id,
                    response.status_code,
                    (time.perf_counter() - started_at) * 1000,
                )
                self.logger.debug(
                    "AI client chat response request_id=%s payload=%s",
                    request_id,
                    preview_object(payload),
                )
                return AiChatResponse.model_validate(payload)
        except httpx.HTTPStatusError as exc:
            self.logger.error(
                "AI client chat http error request_id=%s status=%s elapsed_ms=%.1f body=%r",
                request_id,
                exc.response.status_code,
                (time.perf_counter() - started_at) * 1000,
                exc.response.text[:500],
                exc_info=True,
            )
            raise AiServiceUnavailable(
                f"AI service returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            self.logger.error(
                "AI client chat failed request_id=%s elapsed_ms=%.1f error=%s",
                request_id,
                (time.perf_counter() - started_at) * 1000,
                exc,
                exc_info=True,
            )
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def patient_summary(
        self,
        patient_id: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        self.logger.info(
            "AI client patient summary started base_url=%s request_id=%s patient_id=%s",
            self.base_url,
            request_id,
            patient_id,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/patient-summary",
                    json={"patientId": patient_id},
                    headers=_request_headers(request_id),
                )
                response.raise_for_status()
                payload = response.json()
                self.logger.info(
                    "AI client patient summary completed request_id=%s status=%s elapsed_ms=%.1f",
                    request_id,
                    response.status_code,
                    (time.perf_counter() - started_at) * 1000,
                )
                return payload
        except httpx.HTTPStatusError as exc:
            self.logger.error(
                "AI client patient summary http error request_id=%s status=%s body=%r",
                request_id,
                exc.response.status_code,
                exc.response.text[:500],
            )
            if exc.response.status_code == 404:
                raise AiServiceUnavailable("no_patient_records") from exc
            raise AiServiceUnavailable(
                f"AI service returned HTTP {exc.response.status_code}"
            ) from exc
        except AiServiceUnavailable:
            raise
        except Exception as exc:
            self.logger.error(
                "AI client patient summary failed request_id=%s error=%s",
                request_id,
                exc,
                exc_info=True,
            )
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def analyse_risk(
        self,
        request: RiskAnalysisRequest,
        request_id: str | None = None,
    ) -> RiskAnalysisResponse:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/risk/analyse",
                    json=request.model_dump(exclude_none=True),
                    headers=_request_headers(request_id),
                )
                response.raise_for_status()
                return RiskAnalysisResponse.model_validate(response.json())
        except Exception as exc:
            self.logger.error("AI risk analysis failed request_id=%s error=%s", request_id, exc, exc_info=True)
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def stream_chat(
        self,
        request: ChatRequest,
        request_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        started_at = time.perf_counter()
        self.logger.info(
            "AI client streaming chat started base_url=%s request_id=%s timeout=%s latest_user_preview=%r",
            self.base_url,
            request_id,
            self.timeout,
            _latest_user_preview(request),
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/ai/chat/stream",
                    json=request.model_dump(exclude_none=True),
                    headers=_request_headers(request_id),
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            self.logger.info(
                "AI client streaming chat completed request_id=%s elapsed_ms=%.1f",
                request_id,
                (time.perf_counter() - started_at) * 1000,
            )
        except Exception as exc:
            self.logger.error(
                "AI client streaming chat failed request_id=%s elapsed_ms=%.1f error=%s",
                request_id,
                (time.perf_counter() - started_at) * 1000,
                exc,
                exc_info=True,
            )
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def translate(
        self,
        request: TranslationRequest,
        request_id: str | None = None,
    ) -> AiTranslationResponse:
        started_at = time.perf_counter()
        self.logger.info(
            "AI client translate started base_url=%s request_id=%s timeout=%s target_language=%s text_preview=%r",
            self.base_url,
            request_id,
            self.timeout,
            request.targetLanguage,
            _text_preview(request.text),
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/translate",
                    json=request.model_dump(exclude_none=True),
                    headers=_request_headers(request_id),
                )
                response.raise_for_status()
                payload = response.json()
                self.logger.info(
                    "AI client translate completed request_id=%s status=%s elapsed_ms=%.1f",
                    request_id,
                    response.status_code,
                    (time.perf_counter() - started_at) * 1000,
                )
                return AiTranslationResponse.model_validate(payload)
        except httpx.HTTPStatusError as exc:
            self.logger.error(
                "AI client translate http error request_id=%s status=%s elapsed_ms=%.1f body=%r",
                request_id,
                exc.response.status_code,
                (time.perf_counter() - started_at) * 1000,
                exc.response.text[:500],
                exc_info=True,
            )
            raise AiServiceUnavailable(
                f"AI service returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            self.logger.error(
                "AI client translate failed request_id=%s elapsed_ms=%.1f error=%s",
                request_id,
                (time.perf_counter() - started_at) * 1000,
                exc,
                exc_info=True,
            )
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def task_materials(
        self,
        request: TaskMaterialsRequest,
        request_id: str | None = None,
    ) -> TaskMaterialsResponse:
        started_at = time.perf_counter()
        self.logger.info(
            "AI client task materials started base_url=%s request_id=%s task_label=%r",
            self.base_url,
            request_id,
            request.taskLabel,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/training/task-materials",
                    json=request.model_dump(exclude_none=True),
                    headers=_request_headers(request_id),
                )
                response.raise_for_status()
                payload = response.json()
                self.logger.info(
                    "AI client task materials completed request_id=%s status=%s elapsed_ms=%.1f",
                    request_id,
                    response.status_code,
                    (time.perf_counter() - started_at) * 1000,
                )
                return TaskMaterialsResponse.model_validate(payload)
        except httpx.HTTPStatusError as exc:
            self.logger.error(
                "AI client task materials http error request_id=%s status=%s body=%r",
                request_id,
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise AiServiceUnavailable(
                f"AI service returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            self.logger.error(
                "AI client task materials failed request_id=%s error=%s",
                request_id,
                exc,
                exc_info=True,
            )
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc

    async def transcribe_speech(self, audio: bytes, filename: str, content_type: str, source_language: str, speaker_role: str, client_request_id: str | None) -> SpeechTranscriptionResponse:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/ai/speech/transcribe",
                    files={"audio": (filename, audio, content_type)},
                    data={"sourceLanguage": source_language, "speakerRole": speaker_role, "clientRequestId": client_request_id or ""},
                    headers=_request_headers(client_request_id),
                )
                response.raise_for_status()
                return SpeechTranscriptionResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            raise AiServiceUnavailable(f"AI service returned HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            raise AiServiceUnavailable(f"AI service is unavailable: {exc}") from exc


def _request_headers(request_id: str | None) -> dict[str, str]:
    if not request_id:
        return {}
    return {"x-request-id": request_id}


def _latest_user_preview(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return _text_preview(message.content)
    return ""


def _text_preview(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:180] + ("..." if len(compact) > 180 else "")
