import unittest

from app.repositories.location_monitor import location_alert
from app.repositories.visit_repository import VisitAccessError, VisitRepository


class QueueCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executions = []

    def execute(self, statement, parameters=None):
        self.executions.append((" ".join(statement.split()), parameters))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class LifecycleRepository(VisitRepository):
    def __init__(self, cursor):
        super().__init__()
        self.cursor = cursor

    def _connect(self):
        repository = self

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                class CursorContext:
                    def __enter__(self):
                        return repository.cursor

                    def __exit__(self, *_args):
                        return False

                return CursorContext()

        return Connection()

    def _get_scenario(self, cursor, visit_id):
        return {"visit": {"id": visit_id}}


class DeniedMutationRepository(LifecycleRepository):
    def __init__(self):
        super().__init__(QueueCursor([{"id": "visit-1"}]))
        self.scenario_read = False

    def _visit_row_for_update(self, cursor, visit_id):
        return {
            "id": visit_id,
            "worker_id": "assigned-worker",
            "status": "in_progress",
            "lifecycle_step": "care_tasks",
        }

    def _latest_visit_for_patient(self, cursor, patient_id):
        return "visit-1"

    def _task_id_by_key(self, cursor, visit_id, key):
        return "medication-task"

    def _patient_medications_for_visit(self, cursor, visit_id):
        return ["Medicine A"]

    def _assert_visit_access(self, cursor, visit_id, worker_id, requested_role=None):
        raise VisitAccessError("Worker is not assigned to this visit")

    def _get_scenario(self, cursor, visit_id):
        self.scenario_read = True
        return super()._get_scenario(cursor, visit_id)


class AlertLifecycleTests(unittest.TestCase):
    def test_location_alert_contains_stable_audit_details(self):
        alert = location_alert({
            "type": "check_in",
            "withinExpectedArea": False,
            "distanceFromPlannedMeters": 212.4,
        })

        self.assertEqual(alert["alert_key"], "location-monitor-out-of-range")
        self.assertEqual(alert["payload"]["risk_type"], "location_out_of_range")
        self.assertEqual(alert["payload"]["distance_from_planned_meters"], 212.4)

    def test_later_valid_location_resolves_the_open_location_alert(self):
        cursor = QueueCursor()
        repository = LifecycleRepository(cursor)

        repository._sync_location_alert(
            cursor,
            "visit-1",
            {"type": "check_out", "withinExpectedArea": True},
            "event-1",
        )

        statement, parameters = cursor.executions[-1]
        self.assertIn("status in ('active', 'acknowledged')", statement)
        self.assertEqual(parameters, ("visit-1", "location-monitor-out-of-range"))

    def test_unchanged_risk_does_not_erase_review_state(self):
        cursor = QueueCursor()
        repository = LifecycleRepository(cursor)

        repository._upsert_alert(
            cursor,
            "visit-1",
            {
                "alert_key": "task-risk",
                "level": "moderate",
                "title": "Task risk",
                "message": "Task remains incomplete",
                "payload": {"risk_type": "incomplete"},
            },
            None,
        )

        statement = cursor.executions[-1][0]
        self.assertIn("c3a_app_risk_alerts.payload = excluded.payload", statement)
        self.assertIn("then c3a_app_risk_alerts.status", statement)

    def test_assigned_worker_can_acknowledge_and_action_is_audited(self):
        cursor = QueueCursor([
            {"role": "care_worker", "active": True, "assigned_worker_id": "worker-1"},
            {"id": "alert-1", "status": "active"},
        ])
        repository = LifecycleRepository(cursor)

        result = repository.transition_alert(
            "visit-1", "alert-1", "acknowledge", "worker-1", "care_worker", "Reviewed",
        )

        self.assertEqual(result["visit"]["id"], "visit-1")
        update = next(item for item in cursor.executions if item[0].startswith("update c3a_app_risk_alerts"))
        self.assertIn("acknowledged_at = now()", update[0])
        audit = next(item for item in cursor.executions if item[0].startswith("insert into c3a_app_risk_alert_actions"))
        self.assertEqual(audit[1], ("alert-1", "visit-1", "acknowledged", "active", "acknowledged", "worker-1", "Reviewed"))

    def test_supervisor_can_access_an_unassigned_visit(self):
        cursor = QueueCursor([
            {"role": "supervisor", "active": True, "assigned_worker_id": "worker-1"},
        ])

        LifecycleRepository(cursor)._assert_visit_access(
            cursor, "visit-1", "supervisor-1", "supervisor",
        )

    def test_unassigned_care_worker_is_denied(self):
        cursor = QueueCursor([
            {"role": "care_worker", "active": True, "assigned_worker_id": "worker-1"},
        ])

        with self.assertRaises(VisitAccessError):
            LifecycleRepository(cursor)._assert_visit_access(
                cursor, "visit-1", "worker-2", "care_worker",
            )

    def test_claimed_role_must_match_database_role(self):
        cursor = QueueCursor([
            {"role": "care_worker", "active": True, "assigned_worker_id": "worker-1"},
        ])

        with self.assertRaises(VisitAccessError):
            LifecycleRepository(cursor)._assert_visit_access(
                cursor, "visit-1", "worker-1", "supervisor",
            )

    def test_all_scenario_returning_mutations_gate_access_before_response(self):
        medication_payload = {
            "status": "Completed",
            "hcwId": "unassigned-worker",
            "medicationNames": ["Medicine A"],
            "medicationItems": [{"name": "Medicine A", "takenStatus": "Taken"}],
        }
        operations = (
            lambda repository: repository.start_visit("visit-1", "unassigned-worker", None),
            lambda repository: repository.complete_task("visit-1", "task-1", "unassigned-worker"),
            lambda repository: repository.update_task_status("visit-1", "task-1", "completed", "unassigned-worker"),
            lambda repository: repository.report_task_issue("visit-1", "task-1", "cannot_complete", "unassigned-worker"),
            lambda repository: repository.update_medication_support("visit-1", medication_payload),
            lambda repository: repository.complete_visit("visit-1", "unassigned-worker", None),
            lambda repository: repository.update_patient_profile(
                "patient-1", {}, "visit-1", "unassigned-worker", "care_worker",
            ),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                repository = DeniedMutationRepository()
                with self.assertRaises(VisitAccessError):
                    operation(repository)
                self.assertFalse(repository.scenario_read)


if __name__ == "__main__":
    unittest.main()
