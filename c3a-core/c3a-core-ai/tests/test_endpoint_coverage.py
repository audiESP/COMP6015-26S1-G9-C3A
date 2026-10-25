"""Functional coverage for AI-service endpoints that had no prior test.

Follows the same fake-object pattern as test_chat_orchestration.py: module
globals (service, rag_retriever, db_context_retriever, web_search_service)
are swapped for fakes via patch.object, then real HTTP requests are made
through FastAPI's TestClient so routing, validation, and response shaping
are exercised for real without needing live Ollama/Qdrant/Postgres/Tavily.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

AI_DIR = Path(__file__).resolve().parents[1]
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

os.environ.setdefault("C3A_AI_ENABLED", "false")

import main  # noqa: E402
from db_context import DbContextResult  # noqa: E402
from ollama_service import OllamaServiceError  # noqa: E402
from rag.citations import RetrievedChunk  # noqa: E402
from web_search import WebSearchResult  # noqa: E402


class FakeService:
    def __init__(self):
        self.enabled = True
        self.reply = "Fake generated reply."
        self.error: Exception | None = None
        self.last_messages = None
        self.last_kwargs = None

    def status(self):
        return {"model": "fake", "loaded": True}

    async def check_health(self):
        return self.status()

    async def generate_reply(self, **kwargs):
        self.last_kwargs = kwargs
        self.last_messages = kwargs.get("messages")
        if self.error is not None:
            raise self.error
        return self.reply

    async def translate_text(self, text, target_language, source_language=None):
        if self.error is not None:
            raise self.error
        return {
            "sourceLanguage": source_language or "English",
            "targetLanguage": target_language,
            "translatedText": f"[{target_language}] {text}",
        }


class FakeRagRetriever:
    def __init__(self, configured=True, chunks=None):
        self.is_configured = configured
        self.chunks = chunks if chunks is not None else []
        self.last_query = None
        self.settings = main.rag_retriever.settings

    def status(self):
        return {"status": "fake", "configured": self.is_configured}

    async def retrieve(self, query):
        self.last_query = query
        return self.chunks

    class store:
        @staticmethod
        def search(query, top_k):
            return []


class FakeDbContextRetriever:
    def __init__(self, context="", metadata=None):
        self.context = context
        self.metadata = metadata or {}

    async def patient_summary_context(self, patient_id):
        return DbContextResult(context=self.context, metadata=self.metadata)


class FakeWebSearchService:
    def __init__(self, results=None):
        self.results = results if results is not None else []
        self.last_queries = None
        self.last_task_context = None

    def status(self):
        return {"configured": True, "provider": "fake"}

    async def search(self, queries, task_context, max_results=3):
        self.last_queries = queries
        self.last_task_context = task_context
        return self.results[:max_results]


class AiHealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.patches = [patch.object(main, "service", self.service)]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_health_reports_model_rag_and_web_search_status(self):
        response = self.client.get("/ai/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("rag", body)
        self.assertIn("web_search", body)
        self.assertIn("database_context", body)


class PatientSummaryEndpointTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.db = FakeDbContextRetriever()
        self.patches = [
            patch.object(main, "service", self.service),
            patch.object(main, "db_context_retriever", self.db),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_summary_is_generated_from_database_context(self):
        self.db.context = "### Medications\n[Medication 1] Metformin 500mg"
        self.db.metadata = {"records": [{"category": "medication", "table": "x", "label": "Metformin"}]}
        self.service.reply = "1. Overview\nPatient takes Metformin."

        response = self.client.post("/ai/patient-summary", json={"patientId": "patient-1"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"], "1. Overview\nPatient takes Metformin.")
        self.assertEqual(len(body["records"]), 1)
        self.assertIn("Metformin 500mg", self.service.last_messages[0][1])

    def test_missing_database_context_is_404(self):
        self.db.context = ""

        response = self.client.post("/ai/patient-summary", json={"patientId": "patient-1"})

        self.assertEqual(response.status_code, 404)

    def test_ollama_failure_is_503(self):
        self.db.context = "### Medications\n[Medication 1] Metformin"
        self.service.error = OllamaServiceError("Ollama is down")

        response = self.client.post("/ai/patient-summary", json={"patientId": "patient-1"})

        self.assertEqual(response.status_code, 503)


class RiskAnalyseEndpointTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.patches = [patch.object(main, "service", self.service)]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_valid_json_reply_is_parsed_into_suggestions(self):
        self.service.reply = json.dumps({
            "suggestions": [{
                "riskType": "fall_risk",
                "level": "moderate",
                "confidence": 0.7,
                "reason": "Unsteady after lunch.",
                "recommendedActions": ["Monitor the patient."],
            }]
        })

        response = self.client.post("/ai/risk/analyse", json={"note": "Patient seemed dizzy."})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["suggestions"]), 1)
        self.assertEqual(body["suggestions"][0]["riskType"], "fall_risk")
        self.assertTrue(body["suggestions"][0]["requiresConfirmation"])
        self.assertFalse(body["safetyBoundary"]["diagnosisMade"])
        self.assertFalse(body["safetyBoundary"]["medicationChangeSuggested"])

    def test_malformed_model_reply_falls_back_to_empty_suggestions(self):
        self.service.reply = "not valid json at all"

        response = self.client.post("/ai/risk/analyse", json={"note": "Patient seemed dizzy."})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], [])

    def test_empty_note_is_rejected(self):
        response = self.client.post("/ai/risk/analyse", json={"note": "   "})

        self.assertEqual(response.status_code, 400)

    def test_ollama_failure_is_503(self):
        self.service.error = OllamaServiceError("Ollama is down")

        response = self.client.post("/ai/risk/analyse", json={"note": "Patient seemed dizzy."})

        self.assertEqual(response.status_code, 503)


class TranslateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.patches = [patch.object(main, "service", self.service)]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_translation_is_returned(self):
        response = self.client.post(
            "/ai/translate", json={"text": "Hello", "targetLanguage": "Spanish"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["translatedText"], "[Spanish] Hello")

    def test_empty_text_is_rejected(self):
        response = self.client.post(
            "/ai/translate", json={"text": "  ", "targetLanguage": "Spanish"}
        )

        self.assertEqual(response.status_code, 400)


class RagSearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.rag = FakeRagRetriever()
        self.patches = [patch.object(main, "rag_retriever", self.rag)]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_configured_search_returns_chunks(self):
        self.rag.chunks = [
            RetrievedChunk(
                text="Watch for falls risk and escalate red flags.",
                score=0.8,
                source_title="Falls Guide",
                source_filename="falls-guide.pdf",
                page_start=2,
                page_end=2,
                section_heading="Prevention",
                doc_type="guide",
            )
        ]

        response = self.client.post("/ai/rag/search", json={"query": "falls prevention"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["source_title"], "Falls Guide")
        self.assertEqual(self.rag.last_query, "falls prevention")

    def test_unconfigured_retriever_returns_empty_results(self):
        self.rag.is_configured = False

        response = self.client.post("/ai/rag/search", json={"query": "falls prevention"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_empty_query_is_rejected(self):
        response = self.client.post("/ai/rag/search", json={"query": "  "})

        self.assertEqual(response.status_code, 400)


class TaskMaterialsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.rag = FakeRagRetriever()
        self.web = FakeWebSearchService()
        self.patches = [
            patch.object(main, "rag_retriever", self.rag),
            patch.object(main, "web_search_service", self.web),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_sufficient_internal_results_skip_web_search(self):
        self.rag.chunks = [
            RetrievedChunk(
                text="Internal guidance one.", score=0.9, source_title="Guide A",
                source_filename="a.pdf", page_start=1, page_end=1,
            ),
            RetrievedChunk(
                text="Internal guidance two.", score=0.9, source_title="Guide B",
                source_filename="b.pdf", page_start=1, page_end=1,
            ),
        ]

        response = self.client.post(
            "/ai/training/task-materials",
            json={"taskLabel": "Record medication support", "taskDetail": "Review current medicines."},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["internalCount"], 2)
        self.assertFalse(body["usedWebSearch"])
        self.assertTrue(all(item["sourceType"] == "internal" for item in body["items"]))
        self.assertIsNone(self.web.last_queries)

    def test_thin_internal_results_fall_back_to_web_search(self):
        self.rag.chunks = []
        self.web.results = [
            WebSearchResult(
                title="Falls prevention tips",
                url="https://www.healthdirect.gov.au/falls",
                snippet="Keep walkways clear and encourage regular footwear checks.",
            )
        ]

        response = self.client.post(
            "/ai/training/task-materials",
            json={
                "taskLabel": "Observe mobility and falls risk",
                "taskDetail": "Check walker use and whether gait is steady today.",
                "taskType": "mobility",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["internalCount"], 0)
        self.assertTrue(body["usedWebSearch"])
        self.assertEqual(body["items"][0]["sourceType"], "web")
        self.assertEqual(body["items"][0]["url"], "https://www.healthdirect.gov.au/falls")
        self.assertIsNotNone(self.web.last_queries)

    def test_empty_task_label_is_rejected(self):
        response = self.client.post("/ai/training/task-materials", json={"taskLabel": "  "})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
