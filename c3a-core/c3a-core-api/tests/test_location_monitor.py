import unittest

from app.repositories.location_monitor import (
    derive_location_snapshot,
    haversine_distance_meters,
    location_event_type,
)
from app.repositories.visit_repository import VisitRepository


PLANNED_LAT = -31.9523
PLANNED_LON = 115.8613
NEARBY_LAT = -31.9514
NEARBY_LON = 115.8613


def gps_snapshot(**overrides):
    snapshot = {
        "type": "client_supplied_type",
        "timestamp": "2026-09-03T12:00:00+08:00",
        "coords": {"latitude": NEARBY_LAT, "longitude": NEARBY_LON},
        "permissionStatus": "granted",
        "source": "gps",
        "distanceFromPlannedMeters": 999_999,
        "withinExpectedArea": False,
    }
    snapshot.update(overrides)
    return snapshot


class LocationMonitorTests(unittest.TestCase):
    def test_haversine_distance_is_in_meters(self):
        distance = haversine_distance_meters(PLANNED_LAT, PLANNED_LON, NEARBY_LAT, NEARBY_LON)

        self.assertAlmostEqual(distance, 100.1, delta=0.5)

    def test_client_derived_fields_and_type_are_overwritten(self):
        result = derive_location_snapshot(
            gps_snapshot(),
            snapshot_type="check_in",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=150,
        )

        self.assertEqual(result["type"], "check_in")
        self.assertAlmostEqual(result["distanceFromPlannedMeters"], 100.1, delta=0.5)
        self.assertTrue(result["withinExpectedArea"])

    def test_threshold_boundary_is_inclusive(self):
        distance = haversine_distance_meters(PLANNED_LAT, PLANNED_LON, NEARBY_LAT, NEARBY_LON)
        at_boundary = derive_location_snapshot(
            gps_snapshot(),
            snapshot_type="check_out",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=distance,
        )
        outside = derive_location_snapshot(
            gps_snapshot(),
            snapshot_type="check_out",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=distance - 0.001,
        )

        self.assertTrue(at_boundary["withinExpectedArea"])
        self.assertFalse(outside["withinExpectedArea"])

    def test_missing_plan_or_threshold_clears_client_claims(self):
        for planned_lat, threshold in ((None, 150), (PLANNED_LAT, None)):
            with self.subTest(planned_lat=planned_lat, threshold=threshold):
                result = derive_location_snapshot(
                    gps_snapshot(),
                    snapshot_type="check_in",
                    planned_latitude=planned_lat,
                    planned_longitude=PLANNED_LON,
                    threshold_meters=threshold,
                )
                self.assertIsNone(result["distanceFromPlannedMeters"])
                self.assertIsNone(result["withinExpectedArea"])

    def test_missing_gps_coords_are_recorded_as_unavailable(self):
        result = derive_location_snapshot(
            gps_snapshot(coords=None),
            snapshot_type="check_in",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=150,
        )

        self.assertEqual(result["permissionStatus"], "unavailable")
        self.assertIsNone(result["distanceFromPlannedMeters"])
        self.assertEqual(location_event_type(result, is_check_in=True), "location_permission_denied")

    def test_denied_unavailable_and_manual_override_are_not_distance_checked(self):
        cases = (
            {"permissionStatus": "denied"},
            {"permissionStatus": "unavailable"},
            {"source": "manual_override"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = derive_location_snapshot(
                    gps_snapshot(**overrides),
                    snapshot_type="check_in",
                    planned_latitude=PLANNED_LAT,
                    planned_longitude=PLANNED_LON,
                    threshold_meters=150,
                )
                self.assertIsNone(result["distanceFromPlannedMeters"])
                self.assertIsNone(result["withinExpectedArea"])
                self.assertEqual(location_event_type(result, is_check_in=True), "location_permission_denied")

    def test_event_selection_uses_server_derived_distance_and_endpoint(self):
        outside = derive_location_snapshot(
            gps_snapshot(),
            snapshot_type="check_out",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=50,
        )
        inside = derive_location_snapshot(
            gps_snapshot(),
            snapshot_type="check_in",
            planned_latitude=PLANNED_LAT,
            planned_longitude=PLANNED_LON,
            threshold_meters=150,
        )

        self.assertEqual(location_event_type(outside, is_check_in=False), "location_out_of_range")
        self.assertEqual(location_event_type(inside, is_check_in=True), "location_check_in")
        self.assertEqual(location_event_type(inside, is_check_in=False), "location_check_out")


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


class LocationRepository(VisitRepository):
    def __init__(self):
        super().__init__()
        self.cursor = FakeCursor()
        self.snapshots = []
        self.events = []

    def _connect(self):
        return FakeConnection(self.cursor)

    def _assert_visit_access(self, cursor, visit_id, worker_id, requested_role=None):
        return None

    def _visit_row_for_update(self, cursor, visit_id):
        return {
            "id": visit_id,
            "planned_lat": PLANNED_LAT,
            "planned_lon": PLANNED_LON,
            "location_threshold_meters": 50,
        }

    def _upsert_location_snapshot(self, cursor, visit_id, snapshot):
        self.snapshots.append(snapshot)
        return "snapshot-1"

    def _insert_event(self, cursor, visit_id, event_type, worker_id, **kwargs):
        self.events.append((event_type, kwargs))
        return f"event-{len(self.events)}"

    def _task_id_by_key(self, cursor, visit_id, key):
        return None

    def _event_exists(self, cursor, visit_id, event_type):
        return True

    def _monitor_checklist_task_risks(self, cursor, visit_id):
        return None

    def _get_scenario(self, cursor, visit_id):
        return {"id": visit_id}


class LocationRepositoryTests(unittest.TestCase):
    def test_start_and_complete_use_endpoint_type_and_server_distance(self):
        start_repository = LocationRepository()
        start_repository.start_visit("visit-1", "worker-1", gps_snapshot())

        self.assertEqual(start_repository.snapshots[0]["type"], "check_in")
        self.assertEqual(start_repository.events[0][0], "location_out_of_range")
        self.assertNotEqual(start_repository.snapshots[0]["distanceFromPlannedMeters"], 999_999)

        complete_repository = LocationRepository()
        complete_repository.complete_visit("visit-1", "worker-1", gps_snapshot())

        self.assertEqual(complete_repository.snapshots[0]["type"], "check_out")
        self.assertEqual(complete_repository.events[0][0], "location_out_of_range")


if __name__ == "__main__":
    unittest.main()
