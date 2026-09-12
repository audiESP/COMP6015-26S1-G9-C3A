import subprocess
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from speech.service import SpeechService


class WhisperCppServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(SpeechService)
        self.service.settings = SimpleNamespace(
            backend="whisper_cpp",
            whisper_cpp_binary=Path("/opt/whisper-cli"),
            whisper_cpp_model=Path("/opt/ggml-medium.bin"),
            target_sample_rate=16000,
            max_duration_seconds=20,
            num_threads=4,
        )
        self.service.error = None
        self.service._decode_lock = threading.Lock()

    def test_transcribe_writes_wav_passes_vietnamese_code_and_reads_output(self):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            output_base = Path(command[command.index("-of") + 1])
            output_base.with_suffix(".txt").write_text("xin chào", encoding="utf-8")
            return SimpleNamespace(returncode=0)

        with patch("speech.service.decode_to_pcm", return_value=(b"\x00\x00" * 320, 20)), patch(
            "speech.service.subprocess.run", side_effect=fake_run
        ):
            transcript, duration_ms = self.service.transcribe(b"audio", "audio/m4a", "Vietnamese")

        self.assertEqual(transcript, "xin chào")
        self.assertEqual(duration_ms, 20)
        command = commands[0]
        self.assertEqual(command[command.index("-l") + 1], "vi")
        self.assertIn("-otxt", command)
        self.assertIn("-nt", command)

    def test_unknown_language_uses_auto_detection(self):
        self.assertEqual(self.service._whisper_language_code("A language not in the mapping"), "auto")
        self.assertEqual(self.service._whisper_language_code("vi"), "vi")
