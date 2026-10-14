"""Functional coverage for gateway endpoints that had no prior test.

Each test hits the endpoint through FastAPI's TestClient (so request
validation, routing, and response shaping are exercised for real) while
mocking only the outbound dependency (AiClient or VisitRepository) so the
tests do not need a live AI service or database. unittest.mock.patch
auto-detects async targets and substitutes an AsyncMock, so return_value/
side_effect behave the same as for sync mocks.
"""

import sys
import unittest
from datetime import date
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
from app.ai_client import AiServiceUnavailable
from app.repositories.visit_repository import VisitNotFoundError
from app.schemas import AiChatResponse, AiTranslationResponse, RiskAnalysisResponse, TaskMaterialsResponse


def scenario(**overrides):
    base = {
        "worker": {"id": "worker-1", "name": "Worker One", "role": "care_worker", "shift": "Day"},
        "patient": {"id": "patient-1", "name": "Patient One"},
        "visit": {"id": "visit-1", "patientId": "patient-1", "status": "in_progress"},
        "lifecycleStep": "care_tasks",
        "tasks": [],
        "events": [],
        "alerts": [],
        "incidentChecklist": [],
    }
    base.update(overrides)
    return base


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.database_health_checker.health", return_value={"status": "ok"})
    @patch("main.ai_client.health", return_value={"status": "ok"})
    def test_health_reports_ai_and_database_status(self, _ai_health, _db_health):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "c3a-core-api")
        self.assertEqual(body["ai"]["status"], "ok")
        self.assertEqual(body["database"]["status"], "ok")


class WorkerQueueEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.visit_repository.list_visit_queue")
    def test_worker_visits_are_returned_for_the_requested_date(self, list_visit_queue):
        list_visit_queue.return_value = [
            {
                "id": "visit-1",
                "scheduledAt": "2026-09-04T04:00:00+00:00",
                "patientName": "Patient One",
                "patientMeta": "84 yrs",
                "purpose": "Home visit",
                "status": "scheduled",
            }
        ]

        response = self.client.get("/workers/cw-001/visits", params={"date": "2026-09-04"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["visits"]), 1)
        list_visit_queue.assert_called_once_with("cw-001", date(2026, 9, 4))

    @patch("main.visit_repository.shift_summary")
    def test_shift_summary_is_returned_for_the_requested_date(self, shift_summary):
        shift_summary.return_value = {"total": 3, "completed": 1, "followUps": 0}

        response = self.client.get("/workers/cw-001/shift-summary", params={"date": "2026-09-04"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"total": 3, "completed": 1, "followUps": 0})
        shift_summary.assert_called_once_with("cw-001", date(2026, 9, 4))


class PatientProfileEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.visit_repository.update_patient_profile")
    def test_profile_update_forwards_display_name_and_actor(self, update_patient_profile):
        update_patient_profile.return_value = scenario()

        response = self.client.patch(
            "/patients/patient-1/profile",
            json={
                "visitId": "visit-1",
                "workerId": "worker-1",
                "role": "care_worker",
                "name": "New Name",
                "dietaryNotes": "No change",
            },
        )

        self.assertEqual(response.status_code, 200)
        args, _ = update_patient_profile.call_args
        patient_id, payload, visit_id, worker_id, role = args
        self.assertEqual(patient_id, "patient-1")
        self.assertEqual(payload["displayName"], "New Name")
        self.assertEqual(payload["dietaryNotes"], "No change")
        self.assertEqual((visit_id, worker_id, role), ("visit-1", "worker-1", "care_worker"))


class TaskActionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.visit_repository.complete_task")
    def test_task_complete_forwards_worker_id(self, complete_task):
        complete_task.return_value = scenario()

        response = self.client.post(
            "/visits/visit-1/tasks/task-1/complete",
            json={"workerId": "worker-1", "status": "completed"},
        )

        self.assertEqual(response.status_code, 200)
        complete_task.assert_called_once_with("visit-1", "task-1", "worker-1")

    @patch("main.visit_repository.complete_task")
    def test_task_complete_accepts_no_body(self, complete_task):
        complete_task.return_value = scenario()

        response = self.client.post("/visits/visit-1/tasks/task-1/complete")

        self.assertEqual(response.status_code, 200)
        complete_task.assert_called_once_with("visit-1", "task-1", None)

    @patch("main.visit_repository.report_task_issue")
    def test_task_issue_forwards_type_and_note(self, report_task_issue):
        report_task_issue.return_value = scenario()

        response = self.client.post(
            "/visits/visit-1/tasks/task-1/issue",
            json={"type": "patient_declined", "workerId": "worker-1", "note": "Declined support."},
        )

        self.assertEqual(response.status_code, 200)
        report_task_issue.assert_called_once_with(
            "visit-1", "task-1", "patient_declined", "worker-1", note="Declined support."
        )

    @patch("main.visit_repository.complete_task")
    def test_task_not_found_surfaces_as_404(self, complete_task):
        complete_task.side_effect = VisitNotFoundError("Task task-1 was not found")

        response = self.client.post(
            "/visits/visit-1/tasks/task-1/complete",
            json={"workerId": "worker-1", "status": "completed"},
        )

        self.assertEqual(response.status_code, 404)


class VisitReportEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def _payload(self):
        return {
            "patientContext": {"id": "patient-1", "name": "Patient One"},
            "workerContext": {"id": "worker-1", "name": "Worker One", "role": "care_worker"},
            "visitContext": {"id": "visit-1", "status": "in_progress"},
            "taskContext": [],
            "careOutcomeForm": {"vitals": "stable"},
        }

    @patch("main.ai_client.chat")
    def test_report_generation_returns_ai_reply_as_report_text(self, chat):
        chat.return_value = AiChatResponse(reply="Visit summary text.")

        response = self.client.post("/visits/visit-1/report", json=self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"report": "Visit summary text."})

    @patch("main.ai_client.chat")
    def test_report_generation_surfaces_ai_unavailability_as_502(self, chat):
        chat.side_effect = AiServiceUnavailable("boom")

        response = self.client.post("/visits/visit-1/report", json=self._payload())

        self.assertEqual(response.status_code, 502)


class PatientSummaryEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.ai_client.patient_summary")
    def test_patient_summary_returns_summary_and_records(self, patient_summary):
        patient_summary.return_value = {
            "summary": "Overview text.",
            "records": [{"category": "patient", "table": "x", "label": "y"}],
        }

        response = self.client.get("/patients/patient-1/summary")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"], "Overview text.")
        self.assertEqual(body["patientId"], "patient-1")
        self.assertEqual(len(body["records"]), 1)

    @patch("main.ai_client.patient_summary")
    def test_patient_summary_missing_records_is_404(self, patient_summary):
        patient_summary.side_effect = AiServiceUnavailable("no_patient_records")

        response = self.client.get("/patients/patient-1/summary")

        self.assertEqual(response.status_code, 404)


class RiskAnalyseGatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.ai_client.analyse_risk")
    def test_risk_analysis_is_forwarded_and_returned(self, analyse_risk):
        analyse_risk.return_value = RiskAnalysisResponse(suggestions=[])

        response = self.client.post("/ai/risk/analyse", json={"note": "Patient seemed dizzy."})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], [])

    @patch("main.ai_client.analyse_risk")
    def test_risk_analysis_surfaces_ai_unavailability_as_502(self, analyse_risk):
        analyse_risk.side_effect = AiServiceUnavailable("boom")

        response = self.client.post("/ai/risk/analyse", json={"note": "Patient seemed dizzy."})

        self.assertEqual(response.status_code, 502)


class TranslateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.ai_client.translate")
    def test_translate_returns_translated_text(self, translate):
        translate.return_value = AiTranslationResponse(
            sourceLanguage="English", targetLanguage="Spanish", translatedText="Hola"
        )

        response = self.client.post("/translate", json={"text": "Hello", "targetLanguage": "Spanish"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["translatedText"], "Hola")

    def test_translate_rejects_empty_text(self):
        response = self.client.post("/translate", json={"text": "", "targetLanguage": "Spanish"})

        self.assertEqual(response.status_code, 400)


class TaskMaterialsGatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.ai_client.task_materials")
    def test_task_materials_are_forwarded_and_returned(self, task_materials):
        task_materials.return_value = TaskMaterialsResponse(
            query="Record medication support", items=[], usedWebSearch=False
        )

        response = self.client.post(
            "/training/task-materials",
            json={"taskLabel": "Record medication support", "taskDetail": "Review current medicines."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["query"], "Record medication support")


class UploadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_upload_decodes_and_saves_the_file_and_returns_a_reference(self):
        response = self.client.post(
            "/upload",
            json={"base64": "aGVsbG8=", "mimeType": "text/plain", "filename": "probe.txt"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["fileId"])
        self.assertTrue(body["url"].endswith(".plain"))


if __name__ == "__main__":
    unittest.main()
