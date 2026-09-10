import unittest

from app.repositories.medication_risk_rules import (
    MEDICATION_SUPPORT_ALERT_KEY,
    MEDICATION_SUPPORT_RULES,
    MedicationSupportRule,
    evaluate_medication_support,
)
from app.repositories.visit_repository import VisitRepository


class MedicationRiskRuleTests(unittest.TestCase):
    def test_all_fr6_2_risk_statuses_have_central_rules(self):
        expected = {
            "Delayed": ("medication_delayed", "delayed", "review", "high"),
            "Declined": ("follow_up_required", "follow_up_required", "review", "moderate"),
            "Unavailable": ("follow_up_required", "follow_up_required", "review", "high"),
            "Unable to Confirm": ("follow_up_required", "delayed", "review", "high"),
        }

        for status, values in expected.items():
            with self.subTest(status=status):
                decision = evaluate_medication_support(
                    status,
                    notes="Recorded reason",
                    current_visit_status="in_progress",
                    current_lifecycle_step="care_tasks",
                )
                self.assertEqual(
                    (
                        decision["event_type"],
                        decision["visit_status"],
                        decision["lifecycle_step"],
                        decision["alert"]["level"],
                    ),
                    values,
                )
                self.assertEqual(decision["alert"]["alert_key"], MEDICATION_SUPPORT_ALERT_KEY)
                self.assertIn("Recorded reason", decision["alert"]["message"])

    def test_completed_has_no_risk_and_restores_care_state(self):
        decision = evaluate_medication_support(
            "Completed",
            current_visit_status="follow_up_required",
            current_lifecycle_step="review",
        )

        self.assertEqual(decision["event_type"], "medication_given")
        self.assertEqual(decision["visit_status"], "in_progress")
        self.assertEqual(decision["lifecycle_step"], "care_tasks")
        self.assertIsNone(decision["alert"])

    def test_completed_does_not_reopen_closed_visit(self):
        decision = evaluate_medication_support(
            "Completed",
            current_visit_status="completed",
            current_lifecycle_step="closed",
        )

        self.assertEqual(decision["visit_status"], "completed")
        self.assertEqual(decision["lifecycle_step"], "closed")

    def test_rule_table_can_be_replaced_by_configuration(self):
        configured = dict(MEDICATION_SUPPORT_RULES)
        configured["Delayed"] = MedicationSupportRule(
            event_type="follow_up_required",
            visit_status="review_required",
            lifecycle_step="review",
            level="moderate",
            title="Configured title",
            message="Configured response.",
        )

        decision = evaluate_medication_support(
            "Delayed",
            current_visit_status="in_progress",
            current_lifecycle_step="care_tasks",
            rules=configured,
        )

        self.assertEqual(decision["visit_status"], "review_required")
        self.assertEqual(decision["alert"]["title"], "Configured title")


class FakeCursor:
    def __init__(self):
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.executions.append((" ".join(statement.split()), parameters))


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class MedicationRepository(VisitRepository):
    def __init__(self):
        super().__init__()
        self.cursor = FakeCursor()
        self.events = []
        self.alerts = []

    def _connect(self):
        return FakeConnection(self.cursor)

    def _assert_visit_access(self, cursor, visit_id, worker_id, requested_role=None):
        return None

    def _visit_row_for_update(self, cursor, visit_id):
        return {"worker_id": "worker-1", "status": "in_progress", "lifecycle_step": "care_tasks"}

    def _task_id_by_key(self, cursor, visit_id, key):
        return "task-medication"

    def _patient_medications_for_visit(self, cursor, visit_id):
        return ["Medicine A"]

    def _insert_event(self, cursor, visit_id, event_type, worker_id, **kwargs):
        self.events.append((event_type, kwargs))
        return "event-1"

    def _upsert_alert(self, cursor, visit_id, alert, event_id):
        self.alerts.append((alert, event_id))

    def _get_scenario(self, cursor, visit_id):
        return {"id": visit_id}


def medication_payload(status):
    return {
        "status": status,
        "notes": "Reason supplied" if status != "Completed" else "",
        "hcwId": "worker-1",
        "medicationNames": ["Medicine A"],
        "medicationItems": [{"name": "Medicine A", "takenStatus": "Taken"}],
    }


class MedicationRepositoryTests(unittest.TestCase):
    def test_each_risk_status_upserts_the_same_stable_alert_key(self):
        for status in ("Delayed", "Declined", "Unavailable", "Unable to Confirm"):
            with self.subTest(status=status):
                repository = MedicationRepository()
                repository.update_medication_support("visit-1", medication_payload(status))

                self.assertEqual(len(repository.alerts), 1)
                self.assertEqual(repository.alerts[0][0]["alert_key"], MEDICATION_SUPPORT_ALERT_KEY)
                self.assertEqual(repository.alerts[0][1], "event-1")

    def test_completed_resolves_existing_monitor_alert(self):
        repository = MedicationRepository()

        repository.update_medication_support("visit-1", medication_payload("Completed"))

        self.assertEqual(repository.alerts, [])
        resolution = next(
            execution
            for execution in repository.cursor.executions
            if "set status = 'resolved'" in execution[0]
        )
        self.assertEqual(resolution[1], ("visit-1", MEDICATION_SUPPORT_ALERT_KEY))


if __name__ == "__main__":
    unittest.main()
