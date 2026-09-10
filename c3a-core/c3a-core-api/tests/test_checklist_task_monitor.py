from datetime import datetime, timedelta, timezone
import sys
import types
import unittest

from app.repositories.checklist_task_monitor import (
    checklist_alert_key,
    evaluate_checklist_task,
)

# Repository orchestration is tested without opening a database or requiring its driver.
db_stub = types.ModuleType("app.db")
db_stub.get_database_connection = lambda: None
sys.modules.setdefault("app.db", db_stub)

from app.repositories.visit_repository import VisitRepository


NOW = datetime(2026, 9, 3, 4, 0, tzinfo=timezone.utc)


def task(status: str, due_at: datetime | None = None) -> dict:
    return {
        "id": "task-123",
        "label": "Support lunch routine",
        "type": "meal",
        "status": status,
        "due_at": due_at,
    }


class ChecklistTaskMonitorTests(unittest.TestCase):
    def test_pending_task_past_due_is_overdue(self):
        alert = evaluate_checklist_task(task("pending", NOW - timedelta(minutes=1)), now=NOW)

        self.assertIsNotNone(alert)
        self.assertEqual(alert["payload"]["risk_type"], "overdue")
        self.assertEqual(alert["level"], "moderate")

    def test_pending_task_at_due_time_is_not_yet_overdue(self):
        self.assertIsNone(evaluate_checklist_task(task("pending", NOW), now=NOW))

    def test_pending_task_without_due_time_is_not_overdue(self):
        self.assertIsNone(evaluate_checklist_task(task("pending"), now=NOW))

    def test_delayed_and_issue_tasks_are_incomplete(self):
        for status in ("delayed", "issue"):
            with self.subTest(status=status):
                alert = evaluate_checklist_task(task(status, NOW + timedelta(hours=1)), now=NOW)
                self.assertEqual(alert["payload"]["risk_type"], "incomplete")

    def test_skipped_task_is_missed_even_when_not_due(self):
        alert = evaluate_checklist_task(task("skipped", NOW + timedelta(hours=1)), now=NOW)

        self.assertEqual(alert["payload"]["risk_type"], "missed")

    def test_completed_task_has_no_active_risk(self):
        self.assertIsNone(evaluate_checklist_task(task("completed", NOW - timedelta(hours=1)), now=NOW))

    def test_timezone_offsets_are_compared_as_instants(self):
        perth = timezone(timedelta(hours=8))
        due_at = datetime(2026, 9, 3, 11, 59, tzinfo=perth)

        alert = evaluate_checklist_task(task("pending", due_at), now=NOW)

        self.assertEqual(alert["payload"]["risk_type"], "overdue")
        self.assertEqual(alert["payload"]["due_at"], "2026-09-03T03:59:00+00:00")

    def test_alert_key_is_stable_for_repeated_evaluation(self):
        first = evaluate_checklist_task(task("skipped"), now=NOW)
        second = evaluate_checklist_task(task("skipped"), now=NOW + timedelta(minutes=5))

        self.assertEqual(first["alert_key"], second["alert_key"])
        self.assertEqual(first["alert_key"], checklist_alert_key("task-123"))


class FakeCursor:
    def __init__(self, tasks: list[dict]):
        self.tasks = tasks
        self.executions: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters=None):
        self.executions.append((" ".join(statement.split()), parameters))

    def fetchall(self):
        return self.tasks


class ChecklistTaskRepositorySyncTests(unittest.TestCase):
    def test_scan_upserts_current_risks_and_resolves_stale_monitor_alerts(self):
        cursor = FakeCursor(
            [
                task("skipped"),
                {
                    "id": "task-complete",
                    "label": "Document visit",
                    "type": "documentation",
                    "status": "completed",
                    "due_at": NOW - timedelta(minutes=5),
                },
            ]
        )

        VisitRepository()._monitor_checklist_task_risks(cursor, "visit-123")

        inserts = [entry for entry in cursor.executions if "insert into c3a_app_risk_alerts" in entry[0]]
        resolutions = [entry for entry in cursor.executions if "set status = 'resolved'" in entry[0]]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][1], checklist_alert_key("task-123"))
        self.assertIsNone(inserts[0][1][5])
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0][1][0], "visit-123")
        self.assertEqual(resolutions[0][1][2], [checklist_alert_key("task-123")])

    def test_scan_with_no_risks_resolves_all_active_monitor_alerts(self):
        cursor = FakeCursor([task("completed", NOW - timedelta(minutes=5))])

        VisitRepository()._monitor_checklist_task_risks(cursor, "visit-123")

        inserts = [entry for entry in cursor.executions if "insert into c3a_app_risk_alerts" in entry[0]]
        resolution = next(entry for entry in cursor.executions if "set status = 'resolved'" in entry[0])
        self.assertEqual(inserts, [])
        self.assertEqual(resolution[1][2], [])


if __name__ == "__main__":
    unittest.main()
