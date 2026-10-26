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
        self.last_current_task = None
        self.last_medication_support = None
        self.last_risks = None
        self.last_messages = None
        self.stream_tokens = ["Safe ", "response [Source 1]."]

    def status(self):
        return {"model": "fake", "loaded": True}

    async def generate_reply(self, **kwargs):
        self.last_rag_context = kwargs.get("rag_context")
        self.last_patient = kwargs.get("patient")
        self.last_current_task = kwargs.get("current_task")
        self.last_medication_support = kwargs.get("medication_support")
        self.last_risks = kwargs.get("risks")
        self.last_messages = kwargs.get("messages")
        return self.last_rag_context or "direct reply"

    async def stream_reply(self, **kwargs):
        self.last_rag_context = kwargs.get("rag_context")
        self.last_patient = kwargs.get("patient")
        self.last_current_task = kwargs.get("current_task")
        self.last_medication_support = kwargs.get("medication_support")
        self.last_risks = kwargs.get("risks")
        self.last_messages = kwargs.get("messages")
        for token in self.stream_tokens:
            yield token


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

    def test_recorded_medicine_does_not_become_confirmed_ingestion(self):
        payload = _chat_payload("What medicine is recorded for this patient?")
        payload["patientContext"]["medications"] = ["Medicine A"]
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Medicine A", response.json()["reply"])
        self.assertIn("does not confirm", response.json()["reply"])
        self.assertEqual(response.json()["rag"]["answer_method"], "structured_current_record")
        self.assertIsNone(self.service.last_messages)

    def test_declined_support_does_not_prove_medicine_was_not_taken(self):
        payload = _chat_payload("Can I say this patient took the recorded medicine?")
        payload["medicationSupportContext"] = {"status": "Declined", "medicationNames": ["Medicine A"]}
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("does not confirm whether", response.json()["reply"])
        self.assertNotIn("was not taken", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_unknown_interpreter_flag_remains_unknown(self):
        payload = _chat_payload("Is interpreter support required for this patient?")
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("does not establish whether", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_missing_patient_context_does_not_invent_patient_fact(self):
        response = self.client.post("/ai/chat", json=_chat_payload(
            "What mobility support is recorded for this patient?", patient=False,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn("cannot be determined", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_medication_alert_question_stays_on_risk_path(self):
        payload = _chat_payload("What active medication-related alert is recorded for this patient?")
        payload["riskContext"] = [{"title": "Medication concern", "status": "active"}]
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["rag"].get("answer_method"), "structured_current_record")
        self.assertIsNotNone(self.service.last_messages)

    def test_visit_report_prompt_is_not_replaced_by_medication_direct_reply(self):
        payload = _chat_payload(
            "Generate a standardised home-care visit report for records. "
            "Include Main Matters, Medication Support outcome, and Attention Required."
        )
        payload["workerContext"] = {"id": "worker-1", "name": "Worker One"}
        payload["visitContext"] = {"id": "visit-1", "scheduledAt": "2026-10-26T09:30:00+08:00"}
        payload["medicationSupportContext"] = {
            "status": "Completed",
            "medicationNames": ["Medicine A"],
        }

        response = self.client.post("/ai/chat", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.service.last_messages)
        self.assertNotEqual(
            response.json()["rag"].get("answer_method"),
            "structured_current_record",
        )
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "direct_ai")
        self.assertEqual(self.db.calls, 0)
        self.assertEqual(self.rag.calls, 0)

    def test_updated_task_uses_current_structured_status_without_model(self):
        payload = _chat_payload("What is the status of this patient's current task?")
        payload["messages"] += [
            {"role": "assistant", "content": "The task is pending."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        payload["currentTaskContext"] = {"id": "task-1", "label": "Wellbeing", "status": "completed"}
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("completed", response.json()["reply"])
        self.assertNotIn("pending", response.json()["reply"])
        self.assertEqual(response.json()["rag"]["answer_method"], "structured_current_record")
        self.assertEqual(response.json()["sources"], [])
        self.assertIsNone(self.service.last_messages)

    def test_updated_medication_support_does_not_infer_ingestion(self):
        payload = _chat_payload("What is this patient's recorded medication support outcome?")
        payload["messages"] += [
            {"role": "assistant", "content": "The support outcome was declined."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        payload["medicationSupportContext"] = {"status": "Completed", "medicationNames": ["Medicine A"]}
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Completed", response.json()["reply"])
        self.assertIn("does not confirm", response.json()["reply"])
        self.assertNotIn("declined", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_updated_resolved_risk_is_not_active(self):
        payload = _chat_payload("Which active risk alert applies to this patient now?")
        payload["messages"] += [
            {"role": "assistant", "content": "Falls risk is active."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        payload["riskContext"] = [{"title": "Falls risk", "status": "resolved"}]
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No active risk alert", response.json()["reply"])
        self.assertIn("Falls risk (resolved)", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_updated_absent_medicine_is_reported_as_not_recorded(self):
        payload = _chat_payload("What medicine is recorded for this patient?")
        payload["messages"] += [
            {"role": "assistant", "content": "The patient is taking Medicine A."},
            {"role": "user", "content": "For this patient, use only the current linked record. What is the answer now?"},
        ]
        payload["patientContext"]["medications"] = []
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No medicine is recorded", response.json()["reply"])
        self.assertNotIn("Medicine A", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_updated_mobility_and_interpreter_use_current_fields(self):
        mobility = _chat_payload("What mobility support is recorded for this patient?")
        mobility["messages"] += [
            {"role": "assistant", "content": "The patient uses a wheelchair."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        mobility["patientContext"]["mobilitySupport"] = "Independent walking"
        response = self.client.post("/ai/chat", json=mobility)
        self.assertIn("Independent walking", response.json()["reply"])
        self.assertNotIn("wheelchair", response.json()["reply"])

        communication = _chat_payload("Is an interpreter required for this patient?")
        communication["messages"] += [
            {"role": "assistant", "content": "Yes, an interpreter is required."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        communication["patientContext"].update({"preferredLanguage": "Mandarin", "interpreterRequired": False})
        response = self.client.post("/ai/chat", json=communication)
        self.assertIn("not marked required", response.json()["reply"])
        self.assertNotIn("not needed", response.json()["reply"])

    def test_change_question_does_not_invent_old_structured_record(self):
        payload = _chat_payload("What is the status of this patient's current task?")
        payload["messages"] += [
            {"role": "assistant", "content": "The task is pending."},
            {"role": "user", "content": "What changed in the updated linked record?"},
        ]
        payload["currentTaskContext"] = {"status": "completed"}
        response = self.client.post("/ai/chat", json=payload)
        self.assertIn("cannot verify the exact change", response.json()["reply"])
        self.assertIn("completed", response.json()["reply"])

    def test_updated_record_request_for_advice_still_uses_model(self):
        payload = _chat_payload("What mobility support is recorded for this patient?")
        payload["messages"] += [
            {"role": "assistant", "content": "The patient uses a walker."},
            {"role": "user", "content": "The linked record is updated. What should I do now?"},
        ]
        payload["patientContext"]["mobilitySupport"] = "Independent walking"
        response = self.client.post("/ai/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.service.last_messages)
        self.assertNotEqual(response.json()["rag"].get("answer_method"), "structured_current_record")

    def test_updated_task_stream_uses_same_structured_answer(self):
        payload = _chat_payload("What is the status of this patient's current task?")
        payload["messages"] += [
            {"role": "assistant", "content": "The task is pending."},
            {"role": "user", "content": "This patient's linked record has been updated. What does it say now?"},
        ]
        payload["currentTaskContext"] = {"status": "completed"}
        with self.client.stream("POST", "/ai/chat/stream", json=payload) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]
        self.assertEqual(response.status_code, 200)
        self.assertIn("completed", events[0]["content"])
        self.assertEqual(events[-1]["answerMethod"], "structured_current_record")
        self.assertIsNone(self.service.last_messages)

    def test_database_only_does_not_call_rag(self):
        response = self.client.post(
            "/ai/chat",
            json=_chat_payload("What medications does this patient take?"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.calls, 1)
        self.assertEqual(self.rag.calls, 0)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "database_only")
        self.assertEqual(
            [item["kind"] for item in response.json()["sourceReferences"]],
            ["patient_record", "visit_context"],
        )

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
        guideline = response.json()["sourceReferences"][0]
        self.assertEqual(guideline["kind"], "guideline")
        self.assertEqual(guideline["filename"], "care-guide.pdf")
        self.assertEqual(guideline["pageStart"], 1)
        self.assertEqual(guideline["section"], "Medication monitoring")

    def test_medication_support_and_extended_risks_reach_generation(self):
        payload = _chat_payload("What should I do next?")
        payload["medicationSupportContext"] = {
            "id": "med-1",
            "visitId": "visit-1",
            "status": "partial",
            "notes": "One item was not taken.",
            "timestamp": "2026-09-03T09:10:00Z",
            "hcwId": "worker-1",
            "medicationNames": ["Metformin"],
            "medicationItems": [
                {"name": "Metformin", "takenStatus": "not_taken", "takenAt": None}
            ],
        }
        payload["riskContext"] = [{
            "id": "risk-1",
            "alertKey": "medication:med-1",
            "riskType": "medication_not_taken",
            "level": "high",
            "title": "Medication not taken",
            "message": "Follow-up is required.",
            "status": "acknowledged",
            "details": {"medication": "Metformin"},
            "reviewNote": "Supervisor notified",
        }]

        response = self.client.post("/ai/chat", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.last_medication_support.status, "partial")
        self.assertEqual(self.service.last_medication_support.medicationNames, ["Metformin"])
        self.assertEqual(self.service.last_risks[0].riskType, "medication_not_taken")
        self.assertEqual(self.service.last_risks[0].status, "acknowledged")
        self.assertEqual(self.service.last_risks[0].details["medication"], "Metformin")
        self.assertEqual(self.service.last_risks[0].reviewNote, "Supervisor notified")
        self.assertIn(
            "visit_context",
            [item["kind"] for item in response.json()["sourceReferences"]],
        )

    def test_direct_reply_identifies_general_knowledge(self):
        response = self.client.post("/ai/chat", json=_chat_payload("Hello", patient=False))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sourceReferences"][0]["kind"], "general_knowledge")
        self.assertIn("fake", response.json()["sourceReferences"][0]["label"])

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
        self.assertIsNotNone(self.service.last_patient)
        self.assertIn("patient profile", response.json()["sourceReferences"][-1]["recordTypes"])

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

    def test_current_task_and_conversation_history_reach_generation(self):
        payload = _chat_payload(
            "Based on this patient's current task, what should I do next?"
        )
        payload["messages"] = [
            {"role": "user", "content": "Why is medication support important?"},
            {"role": "assistant", "content": "It helps document safe support."},
            {"role": "user", "content": "What should I do next?"},
        ]
        payload["currentTaskContext"] = {
            "id": "task-medication",
            "label": "Medication support",
            "type": "medication",
            "status": "delayed",
            "dueAt": "09:00",
            "detail": "Confirm the medication support outcome.",
        }

        response = self.client.post("/ai/chat", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rag"]["route"]["effective_mode"], "hybrid")
        self.assertIsNotNone(self.service.last_patient)
        self.assertEqual(self.service.last_current_task.id, "task-medication")
        self.assertEqual(self.service.last_current_task.status, "delayed")
        self.assertEqual(
            self.service.last_messages,
            [
                ("user", "Why is medication support important?"),
                ("assistant", "It helps document safe support."),
                ("user", "What should I do next?"),
            ],
        )

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
        self.assertEqual("".join(event.get("content", "") for event in events), "Safe response [Source 1].")
        self.assertTrue(events[-1]["appendSources"])
        self.assertEqual(len(events[-1]["sources"]), 1)
        self.assertEqual(events[-1]["sourceReferences"][0]["kind"], "guideline")
        self.assertIsNotNone(self.service.last_patient)

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

    def test_risk_analysis_requires_confirmation_and_returns_boundary(self):
        self.service.generate_reply = self._risk_reply
        response = self.client.post(
            "/ai/risk/analyse",
            json={"note": "The medication was not available at the visit."},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["suggestions"][0]["riskType"], "medication_unavailable")
        self.assertTrue(body["suggestions"][0]["requiresConfirmation"])
        self.assertFalse(body["safetyBoundary"]["diagnosisMade"])
        self.assertFalse(body["safetyBoundary"]["medicationChangeSuggested"])

    async def _risk_reply(self, **kwargs):
        return (
            '{"suggestions":[{"riskType":"medication_unavailable",'
            '"level":"high","confidence":0.94,"reason":"Medication was not available",'
            '"recommendedActions":["Record the issue","Contact the supervisor"],'
            '"requiresConfirmation":false}]}'
        )

    def test_uncited_retrieved_guidance_is_not_listed_as_a_source(self):
        self.service.stream_tokens = ["Safe ", "response."]
        with self.client.stream("POST", "/ai/chat/stream", json=_chat_payload(
            "According to the restorative care pathway guide, what does it provide?"
        )) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]
        self.assertEqual(events[-1]["sources"], [])
        self.assertNotIn("guideline", [item["kind"] for item in events[-1]["sourceReferences"]])

    def test_patient_advice_without_linked_patient_is_not_generated(self):
        response = self.client.post("/ai/chat", json=_chat_payload(
            "How should I plan communication with this patient?", patient=False,
        ))
        self.assertIn("No patient record is linked", response.json()["reply"])
        self.assertIsNone(self.service.last_messages)

    def test_medication_support_summary_uses_support_outcome_not_task_status(self):
        payload = _chat_payload("Summarize this patient's medication support record.")
        payload["currentTaskContext"] = {"status": "pending", "type": "wellbeing"}
        payload["medicationSupportContext"] = {"status": "Completed", "medicationNames": ["Medicine A"]}
        reply = self.client.post("/ai/chat", json=payload).json()["reply"]
        self.assertIn("outcome Completed", reply)
        self.assertIn("Medicine A", reply)
        self.assertNotIn("pending", reply)
        self.assertIn("does not confirm", reply)

    def test_medication_support_documentation_names_declined_outcome(self):
        payload = _chat_payload("What should I document about this patient's medication support?")
        payload["medicationSupportContext"] = {"status": "Declined", "medicationNames": ["Medicine A"]}
        reply = self.client.post("/ai/chat", json=payload).json()["reply"]
        self.assertIn("recorded as Declined", reply)
        self.assertIn("declined support", reply)

    def test_ingestion_question_states_recorded_outcome(self):
        payload = _chat_payload("Can I say this patient took the recorded medicine?")
        payload["medicationSupportContext"] = {"status": "Declined", "medicationNames": ["Medicine A"]}
        reply = self.client.post("/ai/chat", json=payload).json()["reply"]
        self.assertIn("recorded as Declined", reply)
        self.assertIn("does not confirm", reply)

    def test_pending_task_is_not_reported_as_late(self):
        payload = _chat_payload("Is this patient's current task on time?")
        payload["currentTaskContext"] = {"status": "pending"}
        reply = self.client.post("/ai/chat", json=payload).json()["reply"]
        self.assertIn("does not show whether it is on time", reply)
        self.assertNotIn("not on time", reply)

    def test_recorded_risk_question_lists_care_risk_flags(self):
        payload = _chat_payload("What mobility risks are recorded for this patient?")
        payload["patientContext"]["mobilitySupport"] = "Independent walking"
        payload["patientContext"]["careRiskFlags"] = ["falls risk"]
        reply = self.client.post("/ai/chat", json=payload).json()["reply"]
        self.assertIn("falls risk", reply)
        self.assertNotIn("No care risk flag", reply)

    def test_condition_specific_guidance_requires_that_condition(self):
        chunk = main.RetrievedChunk(text="Calm the patient.", score=0.9, source_title="Delirium Clinical Care Standard",
                                   source_filename="delirium.pdf", page_start=1, page_end=1)
        unrelated = main.AiChatRequest(**_chat_payload("How should I plan communication with this patient?"))
        self.assertEqual(main._filter_rag_chunks([chunk], unrelated, "How should I plan communication with this patient?"), [])
        payload = _chat_payload("How should I explain this task?")
        payload["patientContext"]["cognitiveStatus"] = "Requires orientation prompts"
        related = main.AiChatRequest(**payload)
        self.assertEqual(main._filter_rag_chunks([chunk], related, "How should I explain this task?"), [chunk])


if __name__ == "__main__":
    unittest.main()
