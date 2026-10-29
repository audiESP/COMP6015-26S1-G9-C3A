import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from speech.service import SpeechService


class _FakeStream:
    def __init__(self):
        self.result = SimpleNamespace(text="")
        self.samples = None

    def accept_waveform(self, sample_rate, samples):
        self.samples = samples


class _FakeRecognizer:
    def __init__(self, language):
        self.language = language

    def create_stream(self):
        return _FakeStream()

    def decode_stream(self, stream):
        stream.result.text = f"{self.language}: transcript"


class _FakeOfflineRecognizer:
    calls = []

    @classmethod
    def from_whisper(cls, **kwargs):
        cls.calls.append(kwargs)
        return _FakeRecognizer(kwargs["language"])


class WhisperOnnxServiceTest(unittest.TestCase):
    def setUp(self):
        _FakeOfflineRecognizer.calls = []
        self.service = SpeechService(
            SimpleNamespace(
                backend="whisper_onnx",
                whisper_onnx_encoder=Path("/models/base-encoder.int8.onnx"),
                whisper_onnx_decoder=Path("/models/base-decoder.int8.onnx"),
                whisper_onnx_tokens=Path("/models/base-tokens.txt"),
                whisper_onnx_cache_size=2,
                target_sample_rate=16000,
                max_duration_seconds=20,
                num_threads=2,
            )
        )

    def test_selected_source_language_conditions_recognizer_and_is_cached(self):
        fake_sherpa = SimpleNamespace(OfflineRecognizer=_FakeOfflineRecognizer)
        pcm = np.zeros(1600, dtype=np.int16).tobytes()
        with patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa}), patch(
            "speech.service.decode_to_pcm", return_value=(pcm, 100)
        ):
            english, _ = self.service.transcribe(b"audio", "audio/wav", "English")
            english_again, _ = self.service.transcribe(b"audio", "audio/wav", "English")
            mandarin, _ = self.service.transcribe(b"audio", "audio/wav", "Mandarin")

        self.assertEqual(english, "en: transcript")
        self.assertEqual(english_again, "en: transcript")
        self.assertEqual(mandarin, "zh: transcript")
        self.assertEqual(
            [call["language"] for call in _FakeOfflineRecognizer.calls], ["en", "zh"]
        )
        self.assertTrue(all(call["tail_paddings"] == 300 for call in _FakeOfflineRecognizer.calls))

    def test_cantonese_uses_whispers_chinese_language_token(self):
        self.assertEqual(self.service._whisper_onnx_language_code("Cantonese"), "zh")

    def test_unknown_language_uses_model_auto_detection(self):
        self.assertEqual(
            self.service._whisper_onnx_language_code("A language not in the mapping"), ""
        )

    def test_collapses_full_question_loop_with_partial_third_copy(self):
        transcript = (
            "did you have enough water today? "
            "did you have enough water today? did"
        )

        self.assertEqual(
            self.service._collapse_whisper_decoder_loop(transcript),
            "did you have enough water today?",
        )

    def test_collapses_three_complete_decoder_copies(self):
        transcript = "please take a seat. please take a seat. please take a seat."

        self.assertEqual(
            self.service._collapse_whisper_decoder_loop(transcript),
            "please take a seat.",
        )

    def test_keeps_two_deliberate_sentence_repetitions(self):
        transcript = "please take a seat. please take a seat."

        self.assertEqual(
            self.service._collapse_whisper_decoder_loop(transcript), transcript
        )

    def test_keeps_short_and_non_periodic_repetitions(self):
        for transcript in (
            "No, no, no.",
            "I said I said that we should wait.",
            "Did you have enough water today? Did you have enough water today? Yes.",
        ):
            with self.subTest(transcript=transcript):
                self.assertEqual(
                    self.service._collapse_whisper_decoder_loop(transcript), transcript
                )
