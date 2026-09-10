"""Rules for detecting checklist task completion risks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


CHECKLIST_ALERT_KEY_PREFIX = "checklist-task-monitor-"


def checklist_alert_key(task_id: object) -> str:
    """Return the stable alert key used to make task monitoring idempotent."""
    return f"{CHECKLIST_ALERT_KEY_PREFIX}{task_id}"


def evaluate_checklist_task(
    task: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return an alert for a missed, overdue, or incomplete task, if any."""
    status = str(task.get("status") or "").lower()
    due_at = task.get("due_at")
    task_id = task.get("id")
    label = str(task.get("label") or "Care task")

    risk_type: str | None = None
    title: str | None = None
    message: str | None = None

    if status == "skipped":
        risk_type = "missed"
        title = "Checklist task was missed"
        message = f'"{label}" was not completed. Review the reason and arrange follow-up if required.'
    elif status in {"delayed", "issue"}:
        risk_type = "incomplete"
        title = "Checklist task is incomplete"
        message = f'"{label}" needs attention before the care activity can be considered complete.'
    elif status == "pending" and _is_overdue(due_at, now or datetime.now(timezone.utc)):
        risk_type = "overdue"
        title = "Checklist task is overdue"
        message = f'"{label}" is past its due time and has not been completed.'

    if risk_type is None:
        return None

    return {
        "alert_key": checklist_alert_key(task_id),
        "level": "moderate",
        "title": title,
        "message": message,
        "payload": {
            "task_id": str(task_id),
            "task_type": task.get("type"),
            "task_status": status,
            "risk_type": risk_type,
            "due_at": _iso_or_none(due_at),
            "triggered_by": "checklist_task_monitor",
        },
    }


def _is_overdue(due_at: Any, now: datetime) -> bool:
    if not isinstance(due_at, datetime):
        return False
    return _as_utc(due_at) < _as_utc(now)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_or_none(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return _as_utc(value).isoformat()
