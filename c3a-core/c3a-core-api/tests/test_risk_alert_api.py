import unittest
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

# Earlier repository tests install a minimal app.db stub when optional database
# dependencies are unavailable. Complete that stub before importing the API app.
if "app.db" in sys.modules and not hasattr(sys.modules["app.db"], "DatabaseHealthChecker"):
    class DatabaseHealthChecker:
        configured = False

        async def health(self):
            return {"status": "not_configured"}

    sys.modules["app.db"].DatabaseHealthChecker = DatabaseHealthChecker
    sys.modules["app.db"].open_database_pool = lambda: None
    sys.modules["app.db"].close_database_pool = lambda: None

from main import app
from app.repositories.visit_repository import VisitAccessError


def scenario(alerts=None):
    return {
        "worker": {"id": "worker-1", "name": "Worker One", "role": "care_worker", "shift": "Day"},
        "patient": {"id": "patient-1", "name": "Patient One"},
        "visit": {"id": "visit-1", "patientId": "patient-1", "status": "in_progress"},
        "lifecycleStep": "care_tasks",
        "tasks": [],
        "events": [],
        "alerts": alerts or [],
        "incidentChecklist": [],
    }


class RiskAlertApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_visit_alert_visibility_requires_explicit_identity(self):
        response = self.client.get("/visits/visit-1")

        self.assertEqual(response.status_code, 422)

    @patch("main.visit_repository.get_scenario")
    def test_visit_identity_is_forwarded_for_database_access_check(self, get_scenario):
        get_scenario.return_value = scenario()

        response = self.client.get(
            "/visits/visit-1",
            params={"workerId": "worker-1", "role": "care_worker"},
        )

        self.assertEqual(response.status_code, 200)
        get_scenario.assert_called_once_with("visit-1", "worker-1", "care_worker")

    @patch("main.visit_repository.transition_alert")
    def test_alert_lifecycle_action_is_forwarded_with_actor_and_note(self, transition_alert):
        transition_alert.return_value = scenario()

        response = self.client.patch(
            "/visits/visit-1/alerts/alert-1",
            json={
                "workerId": "worker-1",
                "role": "care_worker",
                "action": "resolve",
                "note": "Issue checked and resolved",
            },
        )

        self.assertEqual(response.status_code, 200)
        transition_alert.assert_called_once_with(
            "visit-1",
            "alert-1",
            "resolve",
            "worker-1",
            "care_worker",
            "Issue checked and resolved",
        )

    @patch("main.visit_repository.start_visit")
    def test_unauthorised_workflow_mutation_cannot_return_alerts(self, start_visit):
        start_visit.side_effect = VisitAccessError("Worker is not assigned to this visit")

        response = self.client.post(
            "/visits/visit-1/start",
            json={"workerId": "unassigned-worker"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("alerts", response.json())


if __name__ == "__main__":
    unittest.main()
