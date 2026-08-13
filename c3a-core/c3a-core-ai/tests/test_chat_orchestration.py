import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


AI_DIR = Path(__file__).resolve().parents[1]
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

os.environ.setdefault("C3A_AI_ENABLED", "false")

import main  # noqa: E402
from db_context import DbContextResult  # noqa: E402
from rag.citations import RetrievedChunk  # noqa: E402
import ollama_service  # noqa: E402


class FakeService:
    def __init__(self):
        self.last_rag_context = None
        self.last_patient = None

    def status(self):
        return {"model": "fake", "loaded": True}

    async def generate_reply(self, **kwargs):
        self.last_rag_context = kwargs.get("rag_context")
        self.last_patient = kwargs.get("patient")
        return self.last_rag_context or "direct reply"

    async def stream_reply(self, **kwargs):
        self.last_rag_context = kwargs.get("rag_context")
        self.last_patient = kwargs.get("patient")
        yield "Safe "
        yield "response."


class OverlapProbe:
    def __init__(self):
        self.active = 0
        self.overlapped = False

    async def checkpoint(self):
        self.active += 1
        await asyncio.sleep(0.02)
        self.overlapped = self.overlapped or self.active > 1
        self.active -= 1


class FakeDbRetriever:
    enabled = True
    configured = True

    def __init__(self):
        self.calls = 0
        self.probe = None

    def status(self):
        return {"status": "fake"}

    async def retrieve(self, query, patient_context=None):
        self.calls += 1
        if self.probe:
            await self.probe.checkpoint()
        return DbContextResult(
            context=(
                "## Retrieved PostgreSQL Synthetic Patient Context\n"
                "### Medications\n"
                "[Medication 1] Patient: Jane Smith; Medication: Metformin."
            ),
            metadata={
                "enabled_for_chat": True,
                "used_for_chat": True,
                "configured": True,
                "matched_intents": ["patients", "medications"],
                "tables": ["c3a_synthea_medications"],
                "result_counts": {"patients": 1, "medications": 1},
                "status": {"status": "fake"},
            },
        )


class FakeRagRetriever:
    is_configured = True

    def __init__(self, score=0.9):
        self.calls = 0
        self.settings = SimpleNamespace(top_k=main.CHAT_RAG_TOP_K)
        self.score = score
        self.probe = None

    def status(self):
        return {"status": "fake"}

    async def retrieve(self, query):
        self.calls += 1
        if self.probe:
            await self.probe.checkpoint()
        return [
            RetrievedChunk(
                text="Care workers should monitor side effects and escalate red flags.",
                score=self.score,
                source_title="Care Guide",
                source_filename="care-guide.pdf",
                page_start=1,
                page_end=1,
                section_heading="Medication monitoring",
                doc_type="guide",
            )
        ]


def _chat_payload(message, patient=True):
    payload = {"messages": [{"role": "user", "content": message}]}
    if patient:
        payload["patientContext"] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Jane Smith",
        }
    return payload


class ChatOrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.db = FakeDbRetriever()
        self.rag = FakeRagRetriever()
        self.patches = [
            patch.object(main, "service", self.service),
            patch.object(main, "db_context_retriever", self.db),
            patch.object(main, "rag_retriever", self.rag),
            patch.object(main, "CHAT_RAG_ENABLED", True),
            patch.object(main, "CHAT_RAG_MIN_SCORE", 0.0),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_database_only_does_not_call_rag(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload("What medications does this patient take?"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 1)
        self.assertEqual(self.rag.calls, 0)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "database_only")

    def test_rag_only_does_not_call_db(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload(
                "What are safe medication management steps for an older adult at home?",
                patient=False,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 0)
        self.assertEqual(self.rag.calls, 1)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "rag_only")

    def test_linked_patient_general_pathway_question_does_not_call_db(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload(
                "According to the restorative care pathway guide, what is it designed to help older people achieve?"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 0)
        self.assertEqual(self.rag.calls, 1)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "rag_only")
        self.assertIsNone(self.service.last_patient)

    def test_hybrid_combines_db_and_rag_context(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload(
                "Given this patient's medications, what should the care worker monitor today?"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 1)
        self.assertEqual(self.rag.calls, 1)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "hybrid")
        self.assertIsNotNone(self.service.last_patient)
        self.assertIn("## Retrieval Source Boundaries", self.service.last_rag_context)
        self.assertIn("## Retrieved PostgreSQL Synthetic Patient Context", self.service.last_rag_context)
        self.assertIn("## Retrieved Clinical Evidence", self.service.last_rag_context)

    def test_hybrid_retrievals_run_concurrently(self):
        probe = OverlapProbe()
        self.db.probe = probe
        self.rag.probe = probe

        response = self.client.post(
            "/ai/chat",
            json=_chat_payload(
                "Given this patient's medications, what should the care worker monitor today?"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(probe.overlapped)

    def test_prompt_includes_active_task_and_checklist_statuses(self):
        worker = SimpleNamespace(name="Iris Ng", role="care_worker", shift="AM")
        visit = SimpleNamespace(
            id="visit-42",
            scheduledAt="2026-05-12T09:00:00Z",
            arrivedAt="2026-05-12T09:20:00Z",
            location="Home visit",
            status="in_progress",
            plannedAddress="45 Orchard Way",
        )
        tasks = [
            SimpleNamespace(id="t-1", label="Assess patient mobility", status="pending", detail="Patient is unsteady."),
            SimpleNamespace(id="t-2", label="Document observations", status="completed", detail="Completed at 09:45."),
        ]
        checklist = [
            SimpleNamespace(id="c-1", label="Check for dizziness", completed=False),
            SimpleNamespace(id="c-2", label="Confirm fall risk precautions", completed=True),
        ]

        rendered = ollama_service._build_ollama_messages(
            messages=[("user", "What should I do next?")],
            worker=worker,
            visit=visit,
            tasks=tasks,
            events=[],
            risks=[],
            checklist=checklist,
        )

        prompt = "\n".join(message["content"] for message in rendered)
        self.assertIn("## Current Care Tasks", prompt)
        self.assertIn("Assess patient mobility", prompt)
        self.assertIn("## Incident Checklist", prompt)
        self.assertIn("Check for dizziness", prompt)
        self.assertIn("incomplete", prompt.lower())
        self.assertIn("Confirm fall risk precautions", prompt)
        self.assertIn("complete", prompt.lower())

    def test_rag_only_stream_returns_incremental_tokens_and_sources(self):
        with self.client.stream(
            "POST",
            "/ai/chat/stream",
            json=_chat_payload(
                "According to the restorative care pathway guide, what does it provide?"
            ),
        ) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["type"] for event in events], ["token", "token", "done"])
        self.assertEqual("".join(event.get("content", "") for event in events), "Safe response.")
        self.assertTrue(events[-1]["appendSources"])
        self.assertEqual(len(events[-1]["sources"]), 1)
        self.assertIsNone(self.service.last_patient)

    def test_uncertain_resolves_to_hybrid_when_both_sources_have_quality(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload("Show fall risk for residents", patient=False),
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 1)
        self.assertEqual(self.rag.calls, 1)
        self.assertEqual(body["rag"]["route"]["initial_mode"], "uncertain")
        self.assertEqual(body["rag"]["route"]["effective_mode"], "hybrid")
        self.assertEqual(body["rag"]["route"]["ambiguity_resolved_by"], "both_quality")

    def test_low_score_rag_chunk_is_filtered(self):
        self.rag.score = 0.2
        with patch.object(main, "CHAT_RAG_MIN_SCORE", 0.5):
            response = self.client.post(
                "/ai/chat",
                json=_chat_payload("What red flags should a care worker escalate?", patient=False),
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["rag"]["rag_context"]["retrieved_count"], 1)
        self.assertEqual(body["rag"]["rag_context"]["accepted_count"], 0)
        self.assertEqual(body["sources"], [])
        self.assertNotIn("## Retrieved Clinical Evidence", self.service.last_rag_context)


if __name__ == "__main__":
    unittest.main()
