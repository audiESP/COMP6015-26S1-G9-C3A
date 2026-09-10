"""Server-side location snapshot derivation for visit boundary checks."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any, Mapping


EARTH_RADIUS_METERS = 6_371_000.0
UNAVAILABLE_PERMISSION_STATUSES = {"denied", "unavailable"}
LOCATION_ALERT_KEY = "location-monitor-out-of-range"


def location_alert(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the persistent alert for a server-confirmed out-of-range snapshot."""
    if snapshot.get("withinExpectedArea") is not False:
        return None
    snapshot_type = str(snapshot.get("type") or "location")
    distance = snapshot.get("distanceFromPlannedMeters")
    distance_text = f"{float(distance):.0f} m" if distance is not None else "an unknown distance"
    return {
        "alert_key": LOCATION_ALERT_KEY,
        "level": "high",
        "title": "Visit location is outside the expected area",
        "message": f"The {snapshot_type.replace('_', '-')} was recorded {distance_text} from the planned location.",
        "payload": {
            "risk_type": "location_out_of_range",
            "snapshot_type": snapshot_type,
            "distance_from_planned_meters": distance,
            "within_expected_area": False,
            "triggered_by": "location_monitor",
        },
    }


def haversine_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance between two WGS84 points."""
    lat_a, lon_a = radians(float(latitude_a)), radians(float(longitude_a))
    lat_b, lon_b = radians(float(latitude_b)), radians(float(longitude_b))
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    value = sin(delta_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    value = min(1.0, max(0.0, value))
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(value))


def derive_location_snapshot(
    snapshot: Mapping[str, Any],
    *,
    snapshot_type: str,
    planned_latitude: Any,
    planned_longitude: Any,
    threshold_meters: Any,
) -> dict[str, Any]:
    """Replace untrusted client-derived location fields with server calculations."""
    result = dict(snapshot)
    result["type"] = snapshot_type
    result["distanceFromPlannedMeters"] = None
    result["withinExpectedArea"] = None

    source = str(result.get("source") or "manual_override")
    permission = str(result.get("permissionStatus") or "unknown")
    coords = _valid_coords(result.get("coords"))

    if source == "manual_override" or permission in UNAVAILABLE_PERMISSION_STATUSES:
        return result
    if coords is None:
        if source == "gps":
            result["permissionStatus"] = "unavailable"
        return result

    planned = _valid_point(planned_latitude, planned_longitude)
    threshold = _valid_threshold(threshold_meters)
    if planned is None or threshold is None:
        return result

    distance = haversine_distance_meters(
        coords[0],
        coords[1],
        planned[0],
        planned[1],
    )
    result["distanceFromPlannedMeters"] = distance
    result["withinExpectedArea"] = distance <= threshold
    return result


def location_event_type(snapshot: Mapping[str, Any], *, is_check_in: bool) -> str:
    """Select the persisted event from server-derived snapshot data."""
    if (
        snapshot.get("permissionStatus") in UNAVAILABLE_PERMISSION_STATUSES
        or snapshot.get("source") == "manual_override"
    ):
        return "location_permission_denied"
    if snapshot.get("withinExpectedArea") is False:
        return "location_out_of_range"
    return "location_check_in" if is_check_in else "location_check_out"


def _valid_coords(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, Mapping):
        return None
    return _valid_point(value.get("latitude"), value.get("longitude"))


def _valid_point(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _valid_threshold(value: Any) -> float | None:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return None
    return threshold if threshold >= 0 else None
