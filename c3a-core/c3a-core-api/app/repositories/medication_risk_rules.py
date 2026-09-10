"""Configurable rules for medication support risk monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


MEDICATION_SUPPORT_ALERT_KEY = "medication-support-follow-up"


@dataclass(frozen=True)
class MedicationSupportRule:
    event_type: str
    visit_status: str
    lifecycle_step: str
    level: str | None = None
    title: str | None = None
    message: str | None = None


MEDICATION_SUPPORT_RULES: Mapping[str, MedicationSupportRule] = {
    "Completed": MedicationSupportRule(
        event_type="medication_given",
        visit_status="in_progress",
        lifecycle_step="care_tasks",
    ),
    "Delayed": MedicationSupportRule(
        event_type="medication_delayed",
        visit_status="delayed",
        lifecycle_step="review",
        level="high",
        title="Medication support is delayed",
        message="Document the delay, do not double doses, and seek nurse or supervisor advice.",
    ),
    "Declined": MedicationSupportRule(
        event_type="follow_up_required",
        visit_status="follow_up_required",
        lifecycle_step="review",
        level="moderate",
        title="Patient declined medication support",
        message="Record the refusal and reason, then arrange follow-up according to the care plan.",
    ),
    "Unavailable": MedicationSupportRule(
        event_type="follow_up_required",
        visit_status="follow_up_required",
        lifecycle_step="review",
        level="high",
        title="Medication is unavailable",
        message="Record that the medication was unavailable and contact the appropriate supervisor or nurse.",
    ),
    "Unable to Confirm": MedicationSupportRule(
        event_type="follow_up_required",
        visit_status="delayed",
        lifecycle_step="review",
        level="high",
        title="Medication support could not be confirmed",
        message="Do not assume the medication was taken. Document the uncertainty and arrange follow-up.",
    ),
}


def evaluate_medication_support(
    status: str,
    *,
    notes: str = "",
    current_visit_status: str,
    current_lifecycle_step: str,
    rules: Mapping[str, MedicationSupportRule] = MEDICATION_SUPPORT_RULES,
) -> dict[str, object]:
    """Return the event, visit state, and optional alert defined for a status."""
    rule = rules[status]
    visit_status, lifecycle_step = _target_visit_state(
        status,
        rule,
        current_visit_status,
        current_lifecycle_step,
    )
    alert = None
    if rule.level and rule.title and rule.message:
        message = rule.message
        if notes.strip():
            message = f"{message} Details: {notes.strip()}"
        alert = {
            "alert_key": MEDICATION_SUPPORT_ALERT_KEY,
            "level": rule.level,
            "title": rule.title,
            "message": message,
            "payload": {
                "medication_support_status": status,
                "risk_type": _risk_type(status),
                "triggered_by": "medication_support_monitor",
            },
        }

    return {
        "event_type": rule.event_type,
        "visit_status": visit_status,
        "lifecycle_step": lifecycle_step,
        "alert": alert,
    }


def _target_visit_state(
    status: str,
    rule: MedicationSupportRule,
    current_status: str,
    current_lifecycle: str,
) -> tuple[str, str]:
    if current_status == "completed":
        return current_status, current_lifecycle
    if status == "Completed" and current_status not in {
        "scheduled",
        "arrived",
        "delayed",
        "follow_up_required",
    }:
        return current_status, rule.lifecycle_step
    return rule.visit_status, rule.lifecycle_step


def _risk_type(status: str) -> str:
    return status.lower().replace(" ", "_")
