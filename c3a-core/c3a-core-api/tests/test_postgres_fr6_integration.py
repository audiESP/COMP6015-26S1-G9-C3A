"""Opt-in FR6 API-to-PostgreSQL integration tests.

Run with RUN_POSTGRES_INTEGRATION_TESTS=1. Every test uses a dedicated
transaction and rolls it back so the configured database is not polluted.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only in minimal test environments.
    psycopg = None
    dict_row = None


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
INTEGRATION_ENABLED = (
    os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
    and bool(DATABASE_URL)
    and psycopg is not None
)


if psycopg is not None:
    from fastapi.testclient import TestClient

    if "app.db" in sys.modules and not hasattr(sys.modules["app.db"], "DatabaseHealthChecker"):
        class DatabaseHealthChecker:
            configured = False

            async def health(self):
                return {"status": "not_configured"}

        sys.modules["app.db"].DatabaseHealthChecker = DatabaseHealthChecker
        sys.modules["app.db"].open_database_pool = lambda: None
        sys.modules["app.db"].close_database_pool = lambda: None

    import main as api_main
    from app.repositories.visit_repository import VisitRepository


class TransactionalVisitRepository(VisitRepository if psycopg is not None else object):
    """Use one caller-owned transaction instead of committing per request."""

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    @contextmanager
    def _connect(self):
        yield self.connection


@unittest.skipUnless(
    INTEGRATION_ENABLED,
    "Set RUN_POSTGRES_INTEGRATION_TESTS=1 with DATABASE_URL to run PostgreSQL integration tests",
)
class Fr6PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        to_regclass('public.c3a_app_risk_alerts') is not null as alerts_ready,
                        to_regclass('public.c3a_app_risk_alert_actions') is not null as actions_ready,
                        exists (
                            select 1
                            from information_schema.columns
                            where table_schema = 'public'
                              and table_name = 'c3a_app_risk_alerts'
                              and column_name = 'acknowledged_at'
                        ) as lifecycle_ready
                    """
                )
                readiness = cursor.fetchone()
                cursor.execute("select id from c3a_synthea_patients order by id limit 1")
                patient = cursor.fetchone()
        if not all(readiness.values()):
            raise unittest.SkipTest("Apply migrations 001-004 before running PostgreSQL integration tests")
        if not patient:
            raise unittest.SkipTest("The configured database has no c3a_synthea_patients rows")
        cls.patient_id = patient["id"]

    def setUp(self):
        self.connection = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=10,
        )
        self.addCleanup(self._rollback_and_close_connection)
        self.connection.execute("set local statement_timeout = '20s'")
        self.run_id = uuid.uuid4().hex
        self.worker_id = f"codex-it-fr6-worker-{self.run_id}"
        self.external_key = f"codex-it-fr6-visit-{self.run_id}"
        self._create_fixture()

        self.repository = TransactionalVisitRepository(self.connection)
        self.original_repository = api_main.visit_repository
        api_main.visit_repository = self.repository
        self.addCleanup(self._restore_repository)
        self.client = TestClient(api_main.app)
        self.addCleanup(self.client.close)

    def _restore_repository(self):
        api_main.visit_repository = self.original_repository

    def _rollback_and_close_connection(self):
        self.connection.rollback()
        self.connection.close()

    def _create_fixture(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                insert into c3a_app_workers (id, name, role, active, metadata)
                values (%s, 'FR6 Integration Worker', 'care_worker', true, '{}'::jsonb)
                """,
                (self.worker_id,),
            )
            cursor.execute(
                """
                insert into c3a_app_visits (
                    external_key, patient_id, worker_id, scheduled_at, sort_order,
                    purpose, location, planned_address, planned_lat, planned_lon,
                    location_threshold_meters, status, lifecycle_step
                )
                values (
                    %s, %s, %s, now(), 9999,
                    'FR6 integration test', 'Transaction-only test visit',
                    'Transaction-only test address', -31.9523, 115.8613,
                    150, 'scheduled', 'pre_visit'
                )
                returning id::text
                """,
                (self.external_key, self.patient_id, self.worker_id),
            )
            self.visit_id = cursor.fetchone()["id"]

            self.task_ids = {}
            task_rows = (
                ("arrival", "Arrival check", "arrival", "pending", "1 day", 1),
                ("medication", "Medication support", "medication", "pending", "1 day", 2),
                ("overdue", "Overdue wellbeing check", "wellbeing", "pending", "-1 day", 3),
            )
            for task_key, label, task_type, status, due_offset, sort_order in task_rows:
                cursor.execute(
                    """
                    insert into c3a_app_care_tasks (
                        visit_id, task_key, label, type, status, due_at, detail, sort_order
                    )
                    values (%s, %s, %s, %s, %s, now() + %s::interval, %s, %s)
                    returning id::text
                    """,
                    (
                        self.visit_id,
                        task_key,
                        label,
                        task_type,
                        status,
                        due_offset,
                        f"Integration test task: {label}",
                        sort_order,
                    ),
                )
                self.task_ids[task_key] = cursor.fetchone()["id"]

    def _get_alert(self, alert_key: str):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                select id::text, status, payload, acknowledged_by_worker_id,
                       resolved_by_worker_id, review_note
                from c3a_app_risk_alerts
                where visit_id = %s and alert_key = %s
                """,
                (self.visit_id, alert_key),
            )
            return cursor.fetchone()

    def test_checklist_alert_is_idempotent_and_resolves_after_completion(self):
        params = {"workerId": self.worker_id, "role": "care_worker"}

        first = self.client.get(f"/visits/{self.visit_id}", params=params)
        second = self.client.get(f"/visits/{self.visit_id}", params=params)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        alert_key = f"checklist-task-monitor-{self.task_ids['overdue']}"
        matching = [item for item in second.json()["alerts"] if item["alertKey"] == alert_key]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["riskType"], "overdue")
        self.assertEqual(matching[0]["status"], "active")

        completed = self.client.patch(
            f"/visits/{self.visit_id}/tasks/{self.task_ids['overdue']}",
            json={"status": "completed", "workerId": self.worker_id},
        )

        self.assertEqual(completed.status_code, 200, completed.text)
        alert = self._get_alert(alert_key)
        self.assertEqual(alert["status"], "resolved")
        self.assertEqual(alert["payload"]["risk_type"], "overdue")

    def test_medication_alert_actions_are_persisted_and_audited(self):
        response = self.client.patch(
            f"/visits/{self.visit_id}/medication-support",
            json={
                "taskId": self.task_ids["medication"],
                "status": "Delayed",
                "notes": "Medication delivery has not arrived.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hcwId": self.worker_id,
                "medicationNames": ["Integration Medicine"],
                "medicationItems": [
                    {"name": "Integration Medicine", "takenStatus": "Unable to Confirm"}
                ],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        alert = self._get_alert("medication-support-follow-up")
        self.assertIsNotNone(alert)
        self.assertEqual(alert["status"], "active")
        self.assertEqual(alert["payload"]["medication_support_status"], "Delayed")

        acknowledged = self.client.patch(
            f"/visits/{self.visit_id}/alerts/{alert['id']}",
            json={
                "workerId": self.worker_id,
                "role": "care_worker",
                "action": "acknowledge",
                "note": "Reviewed during integration test",
            },
        )
        resolved = self.client.patch(
            f"/visits/{self.visit_id}/alerts/{alert['id']}",
            json={
                "workerId": self.worker_id,
                "role": "care_worker",
                "action": "resolve",
                "note": "Resolved during integration test",
            },
        )

        self.assertEqual(acknowledged.status_code, 200, acknowledged.text)
        self.assertEqual(resolved.status_code, 200, resolved.text)
        final_alert = self._get_alert("medication-support-follow-up")
        self.assertEqual(final_alert["status"], "resolved")
        self.assertEqual(final_alert["acknowledged_by_worker_id"], self.worker_id)
        self.assertEqual(final_alert["resolved_by_worker_id"], self.worker_id)
        self.assertEqual(final_alert["review_note"], "Resolved during integration test")

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                select action, previous_status, resulting_status, actor_worker_id, note
                from c3a_app_risk_alert_actions
                where alert_id = %s
                """,
                (alert["id"],),
            )
            actions = cursor.fetchall()
            cursor.execute(
                """
                select status, notes, medication_items
                from c3a_app_medication_support_records
                where visit_id = %s
                """,
                (self.visit_id,),
            )
            medication_record = cursor.fetchone()

        self.assertEqual({item["action"] for item in actions}, {"acknowledged", "resolved"})
        actions_by_type = {item["action"]: item for item in actions}
        self.assertEqual(actions_by_type["acknowledged"]["previous_status"], "active")
        self.assertEqual(actions_by_type["acknowledged"]["resulting_status"], "acknowledged")
        self.assertEqual(actions_by_type["resolved"]["previous_status"], "acknowledged")
        self.assertEqual(actions_by_type["resolved"]["resulting_status"], "resolved")
        self.assertTrue(all(item["actor_worker_id"] == self.worker_id for item in actions))
        self.assertEqual(medication_record["status"], "Delayed")
        self.assertEqual(medication_record["medication_items"][0]["takenStatus"], "Unable to Confirm")

    def test_location_alert_resolves_after_valid_checkout(self):
        far_check_in = {
            "type": "client-value-is-overwritten",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "coords": {"latitude": -32.0523, "longitude": 115.8613},
            "accuracyMeters": 8,
            "distanceFromPlannedMeters": 0,
            "withinExpectedArea": True,
            "permissionStatus": "granted",
            "source": "gps",
            "note": "Integration test check-in",
        }
        started = self.client.post(
            f"/visits/{self.visit_id}/start",
            json={"workerId": self.worker_id, "checkIn": far_check_in},
        )

        self.assertEqual(started.status_code, 200, started.text)
        check_in = started.json()["visit"]["checkIn"]
        self.assertEqual(check_in["type"], "check_in")
        self.assertFalse(check_in["withinExpectedArea"])
        self.assertGreater(check_in["distanceFromPlannedMeters"], 10_000)
        location_alert = self._get_alert("location-monitor-out-of-range")
        self.assertEqual(location_alert["status"], "active")

        near_check_out = {
            "type": "another-client-value",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "coords": {"latitude": -31.9523, "longitude": 115.8613},
            "accuracyMeters": 5,
            "distanceFromPlannedMeters": 999999,
            "withinExpectedArea": False,
            "permissionStatus": "granted",
            "source": "gps",
            "note": "Integration test check-out",
        }
        completed = self.client.post(
            f"/visits/{self.visit_id}/complete",
            json={"workerId": self.worker_id, "checkOut": near_check_out},
        )

        self.assertEqual(completed.status_code, 200, completed.text)
        check_out = completed.json()["visit"]["checkOut"]
        self.assertEqual(check_out["type"], "check_out")
        self.assertTrue(check_out["withinExpectedArea"])
        self.assertAlmostEqual(check_out["distanceFromPlannedMeters"], 0.0, delta=0.1)
        self.assertEqual(self._get_alert("location-monitor-out-of-range")["status"], "resolved")

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                select type, within_expected_area, distance_from_planned_meters
                from c3a_app_location_snapshots
                where visit_id = %s
                order by type
                """,
                (self.visit_id,),
            )
            snapshots = cursor.fetchall()
            cursor.execute(
                """
                select type
                from c3a_app_visit_events
                where visit_id = %s and type in ('location_out_of_range', 'location_check_out')
                order by occurred_at
                """,
                (self.visit_id,),
            )
            events = [item["type"] for item in cursor.fetchall()]

        self.assertEqual([item["type"] for item in snapshots], ["check_in", "check_out"])
        self.assertEqual(events, ["location_out_of_range", "location_check_out"])

    def test_database_roles_and_visit_assignment_control_alert_visibility(self):
        other_worker_id = f"codex-it-fr6-other-{self.run_id}"
        supervisor_id = f"codex-it-fr6-supervisor-{self.run_id}"
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                insert into c3a_app_workers (id, name, role, active)
                values (%s, 'Other Integration Worker', 'care_worker', true),
                       (%s, 'Integration Supervisor', 'supervisor', true)
                """,
                (other_worker_id, supervisor_id),
            )

        denied = self.client.get(
            f"/visits/{self.visit_id}",
            params={"workerId": other_worker_id, "role": "care_worker"},
        )
        supervisor = self.client.get(
            f"/visits/{self.visit_id}",
            params={"workerId": supervisor_id, "role": "supervisor"},
        )

        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertNotIn("alerts", denied.json())
        self.assertEqual(supervisor.status_code, 200, supervisor.text)
        self.assertEqual(supervisor.json()["visit"]["id"], self.visit_id)


if __name__ == "__main__":
    unittest.main()
