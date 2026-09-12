import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from speech.service import SpeechService


class _FakeStream:
    def __init__(self):
        self.samples = None
        self.result = SimpleNamespace(text="")

    def accept_waveform(self, sample_rate, samples):
        self.samples = samples


class _FakeRecognizer:
    def create_stream(self):
        return _FakeStream()

    def decode_stream(self, stream):
        # The first sample identifies the synthetic VAD segment in this test.
        stream.result.text = {1.0: "first phrase", 2.0: "final phrase"}[float(stream.samples[0])]


class _FakeVad:
    last_instance = None

    def __init__(self, config, buffer_size_in_seconds):
        self.accepted = []
        self.queued = []
        self.flushed = False
        type(self).last_instance = self

    def accept_waveform(self, samples):
        self.accepted.append(samples.copy())
        # Simulate the first segment finishing during normal processing.
        if len(self.accepted) == 1:
            self.queued.append(SimpleNamespace(samples=np.array([1.0], dtype=np.float32)))

    def empty(self):
        return not self.queued

    @property
    def front(self):
        return self.queued[0]

    def pop(self):
        self.queued.pop(0)

    def flush(self):
        self.flushed = True
        # Simulate speech ending exactly when the user releases the button.
        self.queued.append(SimpleNamespace(samples=np.array([2.0], dtype=np.float32)))


class _FakeVadModelConfig:
    def __init__(self):
        self.silero_vad = SimpleNamespace(model=None, min_silence_duration=None, window_size=4)
        self.sample_rate = None


class SpeechServiceVadTest(unittest.TestCase):
    def test_transcribe_processes_partial_tail_and_flushes_final_segment(self):
        service = object.__new__(SpeechService)
        service.settings = SimpleNamespace(
            target_sample_rate=16000,
            vad_model="silero.onnx",
            max_duration_seconds=20,
        )
        service.recognizer = _FakeRecognizer()
        service.vad = object()
        service._decode_lock = threading.Lock()

        fake_sherpa = SimpleNamespace(
            VadModelConfig=_FakeVadModelConfig,
            VoiceActivityDetector=_FakeVad,
        )
        # One complete four-sample window plus a two-sample tail.
        pcm = np.array([1, 1, 1, 1, 2, 2], dtype=np.int16).tobytes()
        with patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa}), patch(
            "speech.service.decode_to_pcm", return_value=(pcm, 120)
        ):
            transcript, duration_ms = service.transcribe(b"audio", "audio/m4a")

        self.assertEqual(transcript, "first phrase final phrase")
        self.assertEqual(duration_ms, 120)
        self.assertTrue(_FakeVad.last_instance.flushed)
        self.assertEqual([len(samples) for samples in _FakeVad.last_instance.accepted], [4, 2])
