from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WHISPER_CPP_MODEL = Path.home() / ".c3a/models/whisper.cpp/ggml-medium.bin"
DEFAULT_WHISPER_ONNX_DIR = Path.home() / ".c3a/models/whisper-base"


def _enabled(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SpeechSettings:
    enabled: bool
    backend: str
    model: Path
    tokens: Path
    vad_model: Path
    whisper_onnx_encoder: Path
    whisper_onnx_decoder: Path
    whisper_onnx_tokens: Path
    whisper_onnx_default_language: str
    whisper_onnx_cache_size: int
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
            backend=os.getenv("SPEECH_BACKEND", "whisper_onnx").strip().lower(),
            model=Path(os.getenv("SPEECH_ASR_MODEL", "")),
            tokens=Path(os.getenv("SPEECH_ASR_TOKENS", "")),
            vad_model=Path(os.getenv("SPEECH_VAD_MODEL", "")),
            whisper_onnx_encoder=Path(
                os.getenv(
                    "SPEECH_WHISPER_ONNX_ENCODER",
                    str(DEFAULT_WHISPER_ONNX_DIR / "base-encoder.int8.onnx"),
                )
            ),
            whisper_onnx_decoder=Path(
                os.getenv(
                    "SPEECH_WHISPER_ONNX_DECODER",
                    str(DEFAULT_WHISPER_ONNX_DIR / "base-decoder.int8.onnx"),
                )
            ),
            whisper_onnx_tokens=Path(
                os.getenv(
                    "SPEECH_WHISPER_ONNX_TOKENS",
                    str(DEFAULT_WHISPER_ONNX_DIR / "base-tokens.txt"),
                )
            ),
            whisper_onnx_default_language=os.getenv(
                "SPEECH_WHISPER_ONNX_DEFAULT_LANGUAGE", "en"
            ).strip().lower(),
            whisper_onnx_cache_size=max(
                1, int(os.getenv("SPEECH_WHISPER_ONNX_CACHE_SIZE", "2"))
            ),
            whisper_cpp_binary=Path(os.getenv("SPEECH_WHISPER_CPP_BINARY", "")),
            whisper_cpp_model=Path(
                os.getenv("SPEECH_WHISPER_CPP_MODEL", str(DEFAULT_WHISPER_CPP_MODEL))
            ),
            num_threads=int(os.getenv("SPEECH_NUM_THREADS", "2")),
            max_duration_seconds=int(os.getenv("SPEECH_MAX_DURATION_SECONDS", "20")),
            max_upload_bytes=int(os.getenv("SPEECH_MAX_UPLOAD_BYTES", "10485760")),
            target_sample_rate=int(os.getenv("SPEECH_TARGET_SAMPLE_RATE", "16000")),
        )
