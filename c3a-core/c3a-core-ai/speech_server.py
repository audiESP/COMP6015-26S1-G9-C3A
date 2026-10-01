"""Dedicated local ASR process entry point for Docker or native-host backends."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from speech.audio import AudioValidationError
from speech.config import SpeechSettings
from speech.service import SpeechService

logger = logging.getLogger(__name__)

speech_service = SpeechService(SpeechSettings.from_env())


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(speech_service.load)
    yield


app = FastAPI(title="C3A Local Speech Service", version="1.0.0", lifespan=lifespan)


class SpeechResult(BaseModel):
    transcript: str
    model: str
    durationMs: int


@app.get("/health")
async def health():
    runtime = "native-host" if speech_service.backend == "whisper_cpp" else "local-docker"
    return {**speech_service.status(), "runtime": runtime}


@app.post("/transcribe", response_model=SpeechResult)
async def transcribe(
    audio: UploadFile = File(...),
    sourceLanguage: str = Form("auto"),
):
    max_bytes = speech_service.settings.max_upload_bytes
    data = await audio.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Audio recording must not be empty")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio recording exceeds the upload limit")
    try:
        transcript, duration_ms = await asyncio.to_thread(
            speech_service.transcribe, data, audio.content_type or "", sourceLanguage
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Keep the client response generic, but retain the original exception and
        # traceback in the speech-service logs for diagnosis.
        logger.exception(
            "Speech transcription failed backend=%s model=%s content_type=%s audio_bytes=%d",
            speech_service.backend,
            speech_service.model_name,
            audio.content_type or "unknown",
            len(data),
        )
        raise HTTPException(status_code=503, detail="Speech recognition service is unavailable") from exc
    return SpeechResult(transcript=transcript, model=speech_service.model_name, durationMs=duration_ms)
