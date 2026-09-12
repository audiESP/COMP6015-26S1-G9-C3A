from __future__ import annotations

import threading
import subprocess
import tempfile
from typing import Any
import wave
from pathlib import Path

import numpy as np

from .audio import AudioValidationError, decode_to_pcm
from .config import SpeechSettings


class SpeechService:
    """Provides a local Omnilingual or native whisper.cpp speech backend."""

    _LANGUAGE_CODES = {
        "arabic": "ar", "chinese": "zh", "mandarin": "zh", "mandarin chinese": "zh",
        "cantonese": "yue", "english": "en", "french": "fr", "german": "de",
        "indonesian": "id", "italian": "it", "japanese": "ja", "korean": "ko",
        "malay": "ms", "spanish": "es", "thai": "th", "vietnamese": "vi",
    }

    def __init__(self, settings: SpeechSettings):
        self.settings = settings
        self.recognizer: Any | None = None
        self.vad: Any | None = None
        self.error: str | None = None
        self._decode_lock = threading.Lock()

    @property
    def backend(self) -> str:
        return getattr(self.settings, "backend", "omnilingual")

    @property
    def model_name(self) -> str:
        if self.backend == "whisper_cpp":
            return f"whisper-cpp:{getattr(self.settings, 'whisper_cpp_model', Path('unknown')).name}"
        return "omnilingual-asr-300m-int8"

    def load(self) -> None:
        if not self.settings.enabled:
            self.error = "Speech recognition is disabled"
            return
        if self.backend == "whisper_cpp":
            binary = self.settings.whisper_cpp_binary
            model = self.settings.whisper_cpp_model
            if not binary.is_file() or not binary.stat().st_mode & 0o111 or not model.is_file():
                self.error = "whisper.cpp binary or model file is not installed"
                return
            self.error = None
            return
        if self.backend != "omnilingual":
            self.error = f"Unsupported speech backend: {self.backend}"
            return
        required = (self.settings.model, self.settings.tokens, self.settings.vad_model)
        if not all(path.is_file() for path in required):
            self.error = "Speech model files are not installed"
            return
        try:
            import sherpa_onnx
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_omnilingual_asr_ctc(
                model=str(self.settings.model), tokens=str(self.settings.tokens), num_threads=self.settings.num_threads,
            )
            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = str(self.settings.vad_model)
            config.silero_vad.min_silence_duration = 0.25
            config.sample_rate = self.settings.target_sample_rate
            self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=self.settings.max_duration_seconds + 2)
            self.error = None
        except Exception as exc:  # Do not expose model paths to callers.
            self.recognizer = self.vad = None
            self.error = f"Speech model initialisation failed: {type(exc).__name__}"

    def status(self) -> dict[str, object]:
        loaded = self.error is None and (
            self.backend == "whisper_cpp" or (self.recognizer is not None and self.vad is not None)
        )
        return {"enabled": self.settings.enabled, "loaded": loaded, "backend": self.backend, "model": self.model_name, "error": self.error}

    def transcribe(self, audio: bytes, content_type: str, source_language: str = "auto") -> tuple[str, int]:
        if self.backend == "whisper_cpp":
            return self._transcribe_with_whisper_cpp(audio, content_type, source_language)
        return self._transcribe_with_omnilingual(audio, content_type)

    def _transcribe_with_omnilingual(self, audio: bytes, content_type: str) -> tuple[str, int]:
        if not self.recognizer or not self.vad:
            raise RuntimeError("Speech recognition is unavailable")
        pcm, duration_ms = decode_to_pcm(audio, content_type, self.settings.target_sample_rate, self.settings.max_duration_seconds)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        with self._decode_lock:
            # The detector is stateful: rebuild it from the same loaded model configuration per utterance.
            import sherpa_onnx
            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = str(self.settings.vad_model)
            vad_config.silero_vad.min_silence_duration = 0.25
            vad_config.sample_rate = self.settings.target_sample_rate
            vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=self.settings.max_duration_seconds + 2)
            window = vad_config.silero_vad.window_size
            texts: list[str] = []

            def decode_available_segments() -> None:
                """Decode every finalized VAD segment before its buffer is reused."""
                while not vad.empty():
                    stream = self.recognizer.create_stream()
                    stream.accept_waveform(self.settings.target_sample_rate, vad.front.samples)
                    vad.pop()
                    self.recognizer.decode_stream(stream)
                    if stream.result.text.strip():
                        texts.append(stream.result.text.strip())

            for start in range(0, len(samples) - window + 1, window):
                vad.accept_waveform(samples[start:start + window])
                decode_available_segments()

            # Feed a partial final VAD window as well. Previously these samples were
            # discarded, which could remove the last syllable or word of an utterance.
            tail_start = len(samples) - (len(samples) % window)
            if tail_start < len(samples):
                vad.accept_waveform(samples[tail_start:])
                decode_available_segments()

            # A release-to-stop recording often has no trailing silence. Flush makes
            # the detector finalize that in-progress speech segment before it is read.
            vad.flush()
            decode_available_segments()

            # Very short utterances may not fill the last VAD window; run direct ASR rather than drop speech.
            if not texts:
                stream = self.recognizer.create_stream()
                stream.accept_waveform(self.settings.target_sample_rate, samples)
                self.recognizer.decode_stream(stream)
                texts.append(stream.result.text.strip())
        transcript = " ".join(text for text in texts if text).strip()
        if not transcript:
            raise AudioValidationError("No speech was detected. Please try again in a quieter location.")
        return transcript, duration_ms

    def _transcribe_with_whisper_cpp(self, audio: bytes, content_type: str, source_language: str) -> tuple[str, int]:
        if self.error is not None:
            raise RuntimeError("Speech recognition is unavailable")
        pcm, duration_ms = decode_to_pcm(audio, content_type, self.settings.target_sample_rate, self.settings.max_duration_seconds)
        language = self._whisper_language_code(source_language)
        with self._decode_lock, tempfile.TemporaryDirectory(prefix="c3a-whisper-") as directory:
            directory_path = Path(directory)
            wav_path = directory_path / "input.wav"
            output_base = directory_path / "transcript"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.settings.target_sample_rate)
                wav.writeframes(pcm)
            command = [
                str(self.settings.whisper_cpp_binary),
                "-m", str(self.settings.whisper_cpp_model),
                "-f", str(wav_path),
                "-l", language,
                "-t", str(self.settings.num_threads),
                "-nt", "-otxt", "-of", str(output_base),
            ]
            try:
                completed = subprocess.run(command, capture_output=True, timeout=90, check=False)
            except subprocess.TimeoutExpired as exc:
                raise AudioValidationError("Speech transcription timed out") from exc
            if completed.returncode:
                raise RuntimeError("whisper.cpp transcription failed")
            transcript_path = output_base.with_suffix(".txt")
            if not transcript_path.is_file():
                raise RuntimeError("whisper.cpp did not produce a transcript")
            transcript = transcript_path.read_text(encoding="utf-8").strip()
        if not transcript:
            raise AudioValidationError("No speech was detected. Please try again in a quieter location.")
        return transcript, duration_ms

    @classmethod
    def _whisper_language_code(cls, source_language: str) -> str:
        value = " ".join(source_language.strip().lower().replace("_", " ").replace("-", " ").split())
        if not value or value in {"auto", "auto detected", "auto detect"}:
            return "auto"
        return cls._LANGUAGE_CODES.get(value, value if len(value) in {2, 3} and value.isalpha() else "auto")
