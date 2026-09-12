from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path


class AudioValidationError(ValueError):
    pass


CONTENT_TYPE_SUFFIX = {
    "audio/m4a": ".m4a", "audio/x-m4a": ".m4a", "audio/mp4": ".m4a",
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg", "audio/webm": ".webm",
}


def decode_to_pcm(audio: bytes, content_type: str, target_sample_rate: int, max_duration_seconds: int) -> tuple[bytes, int]:
    """Decode an allowed mobile recording to temporary mono 16-bit WAV PCM."""
    suffix = CONTENT_TYPE_SUFFIX.get(content_type.lower().split(";", 1)[0])
    if not suffix:
        raise AudioValidationError("Unsupported audio format")
    with tempfile.TemporaryDirectory(prefix="c3a-speech-") as directory:
        source = Path(directory) / f"input{suffix}"
        output = Path(directory) / "normalised.wav"
        source.write_bytes(audio)
        command = [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-ac", "1",
            "-ar", str(target_sample_rate), "-sample_fmt", "s16", "-t", str(max_duration_seconds + 1), str(output),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=30, check=False)
        except FileNotFoundError as exc:
            raise AudioValidationError("Speech audio decoder is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioValidationError("Audio conversion timed out") from exc
        if completed.returncode or not output.exists():
            raise AudioValidationError("Unable to decode audio recording")
        with wave.open(str(output), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != target_sample_rate:
                raise AudioValidationError("Audio normalisation failed")
            frames = wav.getnframes()
            duration = frames / target_sample_rate
            if duration <= 0:
                raise AudioValidationError("Recording contains no audio")
            if duration > max_duration_seconds:
                raise AudioValidationError(f"Recording must be {max_duration_seconds} seconds or shorter")
            return wav.readframes(frames), int(duration * 1000)
