from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _enabled(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SpeechSettings:
    enabled: bool
    backend: str
    model: Path
    tokens: Path
    vad_model: Path
    whisper_cpp_binary: Path
    whisper_cpp_model: Path
    num_threads: int
    max_duration_seconds: int
    max_upload_bytes: int
    target_sample_rate: int

    @classmethod
    def from_env(cls) -> "SpeechSettings":
        return cls(
            enabled=_enabled("SPEECH_ENABLED", False),
            backend=os.getenv("SPEECH_BACKEND", "omnilingual").strip().lower(),
            model=Path(os.getenv("SPEECH_ASR_MODEL", "")),
            tokens=Path(os.getenv("SPEECH_ASR_TOKENS", "")),
            vad_model=Path(os.getenv("SPEECH_VAD_MODEL", "")),
            whisper_cpp_binary=Path(os.getenv("SPEECH_WHISPER_CPP_BINARY", "")),
            whisper_cpp_model=Path(os.getenv("SPEECH_WHISPER_CPP_MODEL", "")),
            num_threads=int(os.getenv("SPEECH_NUM_THREADS", "2")),
            max_duration_seconds=int(os.getenv("SPEECH_MAX_DURATION_SECONDS", "20")),
            max_upload_bytes=int(os.getenv("SPEECH_MAX_UPLOAD_BYTES", "10485760")),
            target_sample_rate=int(os.getenv("SPEECH_TARGET_SAMPLE_RATE", "16000")),
        )
