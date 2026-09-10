import json
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

if "app.db" in sys.modules and not hasattr(sys.modules["app.db"], "DatabaseHealthChecker"):
    class DatabaseHealthChecker:
        configured = False

        async def health(self):
            return {"status": "not_configured"}

    sys.modules["app.db"].DatabaseHealthChecker = DatabaseHealthChecker
    sys.modules["app.db"].open_database_pool = lambda: None
    sys.modules["app.db"].close_database_pool = lambda: None

import main
from app.schemas import AiChatResponse, SourceReference


class FakeAiClient:
    def __init__(self):
        self.request = None

    async def chat(self, request, request_id=None):
        self.request = request
        return AiChatResponse(
            reply="Use the documented medication support outcome.",
            sources=["care-guide.pdf - Medication support - p. 4"],
            sourceReferences=[
                SourceReference(
                    id="guideline-1",
                    kind="guideline",
                    label="Care Guide - p. 4",
                    reason="Retrieved as relevant medication support guidance.",
                    documentTitle="Care Guide",
                    filename="care-guide.pdf",
                    pageStart=4,
                    pageEnd=4,
                    section="Medication support",
                )
            ],
        )

    async def stream_chat(self, request, request_id=None):
        self.request = request
        yield b'{"type":"token","content":"Safe response."}\n'
        yield (
            json.dumps({
                "type": "done",
                "sourceReferences": [{
                    "id": "visit-context",
                    "kind": "visit_context",
                    "label": "Current visit context",
                    "reason": "Used the current task and active alerts.",
                    "recordTypes": ["care tasks", "active risk alerts"],
                }],
                "sources": [],
                "appendSources": False,
            }) + "\n"
        ).encode()


class ChatSourceApiTest(unittest.TestCase):
    def setUp(self):
        self.fake_ai_client = FakeAiClient()
        self.patch = patch.object(main, "ai_client", self.fake_ai_client)
        self.patch.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.patch.stop()

    def test_non_stream_reply_preserves_structured_sources_without_mutating_text(self):
        response = self.client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "What should I do?"}]},
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["reply"], "Use the documented medication support outcome.")
        self.assertNotIn("Sources:", body["reply"])
        self.assertEqual(body["sources"], ["care-guide.pdf - Medication support - p. 4"])
        self.assertEqual(body["sourceReferences"][0]["kind"], "guideline")
        self.assertEqual(body["sourceReferences"][0]["pageStart"], 4)

    def test_context_and_streamed_source_references_pass_through(self):
        payload = {
            "messages": [{"role": "user", "content": "What needs follow-up?"}],
            "medicationSupportContext": {
                "visitId": "visit-1",
                "status": "partial",
                "timestamp": "2026-09-03T09:10:00Z",
                "hcwId": "worker-1",
                "medicationNames": ["Warfarin"],
                "medicationItems": [{"name": "Warfarin", "takenStatus": "not_taken"}],
            },
            "riskContext": [{
                "id": "risk-1",
                "riskType": "medication_not_taken",
                "level": "high",
                "title": "Medication not taken",
                "status": "acknowledged",
                "details": {"medication": "Warfarin"},
                "reviewNote": "Supervisor notified",
            }],
        }

        with self.client.stream("POST", "/chat/stream", json=payload) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[-1]["sourceReferences"][0]["kind"], "visit_context")
        self.assertEqual(self.fake_ai_client.request.medicationSupportContext.status, "partial")
        self.assertEqual(self.fake_ai_client.request.riskContext[0].riskType, "medication_not_taken")
        self.assertEqual(self.fake_ai_client.request.riskContext[0].reviewNote, "Supervisor notified")


if __name__ == "__main__":
    unittest.main()
