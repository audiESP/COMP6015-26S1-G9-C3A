import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class VisitDatesApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("main.visit_repository.list_visit_dates")
    def test_worker_visit_dates_are_returned_for_calendar_range(self, list_visit_dates):
        list_visit_dates.return_value = ["2026-10-01", "2026-10-15"]

        response = self.client.get(
            "/workers/cw-001/visit-dates",
            params={"start": "2026-10-01", "end": "2026-11-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"dates": ["2026-10-01", "2026-10-15"]})
        list_visit_dates.assert_called_once_with(
            "cw-001",
            date(2026, 10, 1),
            date(2026, 11, 1),
        )

    def test_worker_visit_dates_require_valid_dates(self):
        response = self.client.get(
            "/workers/cw-001/visit-dates",
            params={"start": "October", "end": "2026-11-01"},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
