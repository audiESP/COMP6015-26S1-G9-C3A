"""Database-backed visit workflow repository."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from app.db import get_database_connection
from app.repositories.checklist_task_monitor import (
    CHECKLIST_ALERT_KEY_PREFIX,
    evaluate_checklist_task,
)
from app.repositories.location_monitor import (
    LOCATION_ALERT_KEY,
    derive_location_snapshot,
    location_alert,
    location_event_type,
)
from app.repositories.medication_risk_rules import (
    MEDICATION_SUPPORT_ALERT_KEY,
    MEDICATION_SUPPORT_RULES,
    evaluate_medication_support,
)


class VisitRepositoryError(Exception):
    """Base class for visit repository errors."""


class VisitNotFoundError(VisitRepositoryError):
    """Raised when a visit cannot be found."""


class VisitRepositoryUnavailable(VisitRepositoryError):
    """Raised when the database is not configured."""


class VisitValidationError(VisitRepositoryError):
    """Raised when a visit workflow payload is invalid."""


class VisitAccessError(VisitRepositoryError):
    """Raised when a worker cannot view or change a visit alert."""


MEDICATION_SUPPORT_STATUSES = set(MEDICATION_SUPPORT_RULES)

MEDICATION_TAKEN_STATUSES = {
    "Taken",
    "Not Taken",
    "Unable to Confirm",
}


class VisitRepository:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        if not self.database_url:
            raise VisitRepositoryUnavailable("DATABASE_URL is not configured")
        return get_database_connection()

    def list_visit_queue(self, worker_id: str, shift_date: date) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                return self._list_visit_queue(cursor, worker_id, shift_date)

    def get_scenario(
        self,
        visit_id: str,
        requester_worker_id: str,
        requester_role: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._assert_visit_access(cursor, visit_id, requester_worker_id, requester_role)
                return self._get_scenario(cursor, visit_id)

    def transition_alert(
        self,
        visit_id: str,
        alert_id: str,
        action: str,
        worker_id: str,
        role: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        target_status = {
            "acknowledge": "acknowledged",
            "resolve": "resolved",
            "dismiss": "dismissed",
        }.get(action)
        if target_status is None:
            raise VisitValidationError("Alert action is not supported")
        clean_note = (note or "").strip() or None

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._assert_visit_access(cursor, visit_id, worker_id, role)
                cursor.execute(
                    """
                    select id, status
                    from c3a_app_risk_alerts
                    where id = %s and visit_id = %s
                    for update
                    """,
                    (alert_id, visit_id),
                )
                alert = cursor.fetchone()
                if not alert:
                    raise VisitNotFoundError(f"Alert {alert_id} was not found for visit {visit_id}")
                previous_status = alert["status"]
                if previous_status in ("resolved", "dismissed"):
                    raise VisitValidationError("A closed alert cannot be changed")
                if previous_status == target_status:
                    return self._get_scenario(cursor, visit_id)

                timestamp_column = {
                    "acknowledged": "acknowledged_at",
                    "resolved": "resolved_at",
                    "dismissed": "dismissed_at",
                }[target_status]
                actor_column = {
                    "acknowledged": "acknowledged_by_worker_id",
                    "resolved": "resolved_by_worker_id",
                    "dismissed": "dismissed_by_worker_id",
                }[target_status]
                cursor.execute(
                    f"""
                    update c3a_app_risk_alerts
                    set status = %s,
                        {timestamp_column} = now(),
                        {actor_column} = %s,
                        review_note = coalesce(%s, review_note),
                        updated_at = now()
                    where id = %s
                    """,
                    (target_status, worker_id, clean_note, alert_id),
                )
                cursor.execute(
                    """
                    insert into c3a_app_risk_alert_actions (
                        alert_id, visit_id, action, previous_status,
                        resulting_status, actor_worker_id, note
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (alert_id, visit_id, target_status, previous_status, target_status, worker_id, clean_note),
                )
                return self._get_scenario(cursor, visit_id)

    def update_patient_profile(
        self,
        patient_id: str,
        payload: dict[str, Any],
        visit_id: str,
        worker_id: str,
        requested_role: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id::text from c3a_app_visits where id = %s and patient_id = %s",
                    (visit_id, patient_id),
                )
                if not cursor.fetchone():
                    raise VisitNotFoundError(f"Visit {visit_id} was not found for patient {patient_id}")
                self._assert_visit_access(cursor, visit_id, worker_id, requested_role)
                cursor.execute(
                    """
                    insert into c3a_app_patient_profiles (
                        patient_id,
                        display_name,
                        medical_record_number,
                        diagnosis_summary,
                        notes,
                        preferred_language,
                        interpreter_required,
                        cultural_background,
                        mobility_support,
                        cognitive_status,
                        dietary_notes,
                        communication_notes,
                        care_risk_flags,
                        allergies_override,
                        medications_override,
                        updated_at
                    )
                    values (
                        %(patient_id)s,
                        %(display_name)s,
                        %(medical_record_number)s,
                        %(diagnosis_summary)s,
                        %(notes)s,
                        %(preferred_language)s,
                        %(interpreter_required)s,
                        %(cultural_background)s,
                        %(mobility_support)s,
                        %(cognitive_status)s,
                        %(dietary_notes)s,
                        %(communication_notes)s,
                        %(care_risk_flags)s::jsonb,
                        %(allergies_override)s::jsonb,
                        %(medications_override)s::jsonb,
                        now()
                    )
                    on conflict (patient_id) do update
                    set display_name = excluded.display_name,
                        medical_record_number = excluded.medical_record_number,
                        diagnosis_summary = excluded.diagnosis_summary,
                        notes = excluded.notes,
                        preferred_language = excluded.preferred_language,
                        interpreter_required = excluded.interpreter_required,
                        cultural_background = excluded.cultural_background,
                        mobility_support = excluded.mobility_support,
                        cognitive_status = excluded.cognitive_status,
                        dietary_notes = excluded.dietary_notes,
                        communication_notes = excluded.communication_notes,
                        care_risk_flags = excluded.care_risk_flags,
                        allergies_override = excluded.allergies_override,
                        medications_override = excluded.medications_override,
                        updated_at = now()
                    """,
                    {
                        "patient_id": patient_id,
                        "display_name": payload.get("displayName"),
                        "medical_record_number": payload.get("medicalRecordNumber"),
                        "diagnosis_summary": payload.get("diagnosis"),
                        "notes": payload.get("notes"),
                        "preferred_language": payload.get("preferredLanguage"),
                        "interpreter_required": payload.get("interpreterRequired"),
                        "cultural_background": payload.get("culturalBackground"),
                        "mobility_support": payload.get("mobilitySupport"),
                        "cognitive_status": payload.get("cognitiveStatus"),
                        "dietary_notes": payload.get("dietaryNotes"),
                        "communication_notes": payload.get("communicationNotes"),
                        "care_risk_flags": _json_array(payload.get("careRiskFlags")),
                        "allergies_override": _json_array_or_none(payload.get("allergies")),
                        "medications_override": _json_array_or_none(payload.get("medications")),
                    },
                )
                return self._get_scenario(cursor, visit_id)

    def start_visit(self, visit_id: str, worker_id: str | None, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                visit = self._visit_row_for_update(cursor, visit_id)
                self._assert_visit_access(cursor, visit_id, worker_id)
                snapshot = _derive_location_snapshot(snapshot, visit, "check_in") if snapshot else None
                snapshot_id = self._upsert_location_snapshot(cursor, visit_id, snapshot) if snapshot else None
                if snapshot_id:
                    event_type = location_event_type(snapshot, is_check_in=True)
                    event_id = self._insert_event(cursor, visit_id, event_type, worker_id, location_snapshot_id=snapshot_id, note=snapshot.get("note"))
                    self._sync_location_alert(cursor, visit_id, snapshot, event_id)

                now_sql = "coalesce(arrived_at, now())"
                cursor.execute(
                    f"""
                    update c3a_app_visits
                    set status = 'in_progress',
                        lifecycle_step = 'care_tasks',
                        arrived_at = {now_sql},
                        updated_at = now()
                    where id = %s
                    """,
                    (visit["id"],),
                )
                arrival_task_id = self._task_id_by_key(cursor, visit_id, "arrival")
                if arrival_task_id:
                    cursor.execute(
                        """
                        update c3a_app_care_tasks
                        set status = 'completed',
                            completed_at = coalesce(completed_at, now()),
                            updated_at = now()
                        where id = %s
                        """,
                        (arrival_task_id,),
                    )
                if not self._event_exists(cursor, visit_id, "arrived"):
                    self._insert_event(cursor, visit_id, "arrived", worker_id, task_id=arrival_task_id)
                if not self._event_exists(cursor, visit_id, "care_started"):
                    self._insert_event(cursor, visit_id, "care_started", worker_id)
                return self._get_scenario(cursor, visit_id)

    def complete_task(self, visit_id: str, task_id: str, worker_id: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._visit_row_for_update(cursor, visit_id)
                self._assert_visit_access(cursor, visit_id, worker_id)
                task = self._task_row_for_update(cursor, visit_id, task_id)
                cursor.execute(
                    """
                    update c3a_app_care_tasks
                    set status = 'completed',
                        completed_at = coalesce(completed_at, now()),
                        updated_at = now()
                    where id = %s
                    """,
                    (task["id"],),
                )
                cursor.execute(
                    """
                    update c3a_app_visits
                    set status = case
                            when status in ('scheduled', 'arrived') then 'in_progress'
                            else status
                        end,
                        lifecycle_step = case
                            when lifecycle_step in ('pre_visit', 'arrival') then 'care_tasks'
                            else lifecycle_step
                        end,
                        updated_at = now()
                    where id = %s
                    """,
                    (visit_id,),
                )
                if task["type"] == "medication":
                    self._insert_event(cursor, visit_id, "medication_given", worker_id, task_id=task["id"])
                return self._get_scenario(cursor, visit_id)

    def update_task_status(self, visit_id: str, task_id: str, status: str, worker_id: str | None = None, note: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                visit = self._visit_row_for_update(cursor, visit_id)
                if visit["status"] == "completed":
                    raise VisitValidationError("This visit is closed")
                self._assert_visit_access(cursor, visit_id, worker_id)
                self._task_row_for_update(cursor, visit_id, task_id)
                cursor.execute(
                    """
                    update c3a_app_care_tasks
                    set status = %s,
                        status_note = coalesce(%s, status_note),
                        completed_at = case when %s = 'completed' then coalesce(completed_at, now()) else null end,
                        updated_at = now()
                    where id = %s
                    """,
                    (status, note, status, task_id),
                )
                cursor.execute(
                    """
                    update c3a_app_visits
                    set status = case
                            when status in ('scheduled', 'arrived') then 'in_progress'
                            else status
                        end,
                        lifecycle_step = case
                            when lifecycle_step in ('pre_visit', 'arrival') then 'care_tasks'
                            else lifecycle_step
                        end,
                        updated_at = now()
                    where id = %s
                    """,
                    (visit_id,),
                )
                if status == "completed" and self._task_type(cursor, task_id) == "medication":
                    self._insert_event(cursor, visit_id, "medication_given", worker_id, task_id=task_id)
                return self._get_scenario(cursor, visit_id)

    def report_task_issue(self, visit_id: str, task_id: str, issue_type: str, worker_id: str | None = None, note: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._visit_row_for_update(cursor, visit_id)
                self._assert_visit_access(cursor, visit_id, worker_id)
                task = self._task_row_for_update(cursor, visit_id, task_id)
                event_type, task_status, visit_status, lifecycle, alert = _issue_mapping(task, issue_type)
                note = f"{_issue_note(task, issue_type)} {note.strip()}" if note and note.strip() else _issue_note(task, issue_type)
                cursor.execute(
                    """
                    update c3a_app_care_tasks
                    set status = %s,
                        status_note = %s,
                        updated_at = now()
                    where id = %s
                    """,
                    (task_status, note, task["id"]),
                )
                cursor.execute(
                    """
                    update c3a_app_visits
                    set status = %s,
                        lifecycle_step = %s,
                        updated_at = now()
                    where id = %s
                    """,
                    (visit_status, lifecycle, visit_id),
                )
                event_id = self._insert_event(cursor, visit_id, event_type, worker_id, task_id=task["id"], note=note)
                alert["payload"] = {
                    "task_id": str(task["id"]),
                    "task_type": task["type"],
                    "task_status": task_status,
                    "issue_type": issue_type,
                    "triggered_by": "task_issue",
                }
                self._upsert_alert(cursor, visit_id, alert, event_id)
                return self._get_scenario(cursor, visit_id)

    def update_medication_support(self, visit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = payload.get("status")
        notes = (payload.get("notes") or "").strip()
        if status not in MEDICATION_SUPPORT_STATUSES:
            raise VisitValidationError("Medication support status is not supported")
        if status != "Completed" and not notes:
            raise VisitValidationError("Notes or reasons are required when medication support is not completed")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                visit = self._visit_row_for_update(cursor, visit_id)
                worker_id = payload.get("hcwId")
                self._assert_visit_access(cursor, visit_id, worker_id)
                task_id = payload.get("taskId") or self._task_id_by_key(cursor, visit_id, "medication")
                if not task_id:
                    raise VisitValidationError("This visit does not have a medication support task")
                medication_names = payload.get("medicationNames") or self._patient_medications_for_visit(cursor, visit_id)
                medication_items = _normalise_medication_items(payload.get("medicationItems"), medication_names)
                recorded_at = payload.get("timestamp") or datetime.now(timezone.utc)
                cursor.execute(
                    """
                    insert into c3a_app_medication_support_records (
                        visit_id,
                        task_id,
                        hcw_id,
                        status,
                        notes,
                        recorded_at,
                        medication_names,
                        medication_items,
                        updated_at
                    )
                    values (
                        %(visit_id)s,
                        %(task_id)s,
                        %(hcw_id)s,
                        %(status)s,
                        %(notes)s,
                        %(recorded_at)s,
                        %(medication_names)s::jsonb,
                        %(medication_items)s::jsonb,
                        now()
                    )
                    on conflict (visit_id) do update
                    set task_id = excluded.task_id,
                        hcw_id = excluded.hcw_id,
                        status = excluded.status,
                        notes = excluded.notes,
                        recorded_at = excluded.recorded_at,
                        medication_names = excluded.medication_names,
                        medication_items = excluded.medication_items,
                        updated_at = now()
                    """,
                    {
                        "visit_id": visit_id,
                        "task_id": task_id,
                        "hcw_id": worker_id,
                        "status": status,
                        "notes": notes or None,
                        "recorded_at": recorded_at,
                        "medication_names": _json_array(medication_names),
                        "medication_items": _json_array(medication_items),
                    },
                )
                cursor.execute(
                    """
                    update c3a_app_care_tasks
                    set status = 'completed',
                        completed_at = coalesce(completed_at, now()),
                        status_note = %s,
                        updated_at = now()
                    where id = %s
                    """,
                    (f"Medication support status: {status}" + (f" - {notes}" if notes else ""), task_id),
                )
                decision = evaluate_medication_support(
                    status,
                    notes=notes,
                    current_visit_status=visit["status"],
                    current_lifecycle_step=visit["lifecycle_step"],
                )
                cursor.execute(
                    """
                    update c3a_app_visits
                    set status = %s,
                        lifecycle_step = %s,
                        updated_at = now()
                    where id = %s
                    """,
                    (decision["visit_status"], decision["lifecycle_step"], visit_id),
                )
                event_id = self._insert_event(
                    cursor,
                    visit_id,
                    decision["event_type"],
                    worker_id,
                    task_id=task_id,
                    note=f"{status}: {notes}" if notes else status,
                )
                if decision["alert"] is not None:
                    self._upsert_alert(
                        cursor,
                        visit_id,
                        decision["alert"],
                        event_id,
                    )
                else:
                    cursor.execute(
                        """
                        update c3a_app_risk_alerts
                        set status = 'resolved',
                            resolved_at = now(),
                            resolved_by_worker_id = null,
                            updated_at = now()
                        where visit_id = %s
                          and alert_key = %s
                          and status in ('active', 'acknowledged')
                        """,
                        (visit_id, MEDICATION_SUPPORT_ALERT_KEY),
                    )
                return self._get_scenario(cursor, visit_id)

    def complete_visit(self, visit_id: str, worker_id: str | None, snapshot: dict[str, Any] | None, report: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                visit = self._visit_row_for_update(cursor, visit_id)
                self._assert_visit_access(cursor, visit_id, worker_id)
                self._monitor_checklist_task_risks(cursor, visit_id)
                snapshot = _derive_location_snapshot(snapshot, visit, "check_out") if snapshot else None
                snapshot_id = self._upsert_location_snapshot(cursor, visit_id, snapshot) if snapshot else None
                if snapshot_id:
                    event_type = location_event_type(snapshot, is_check_in=False)
                    event_id = self._insert_event(cursor, visit_id, event_type, worker_id, location_snapshot_id=snapshot_id, note=snapshot.get("note"))
                    self._sync_location_alert(cursor, visit_id, snapshot, event_id)
                cursor.execute(
                    """
                    update c3a_app_care_tasks
                    set status = 'skipped',
                        updated_at = now()
                    where visit_id = %s
                      and status = 'pending'
                    """,
                    (visit_id,),
                )
                cursor.execute(
                    """
                    update c3a_app_visits
                    set status = 'completed',
                        lifecycle_step = 'closed',
                        completed_at = coalesce(completed_at, now()),
                        updated_at = now()
                    where id = %s
                    """,
                    (visit_id,),
                )
                self._insert_event(cursor, visit_id, "visit_completed", worker_id, note=report)
                return self._get_scenario(cursor, visit_id)

    def shift_summary(self, worker_id: str, shift_date: date) -> dict[str, int]:
        queue = self.list_visit_queue(worker_id, shift_date)
        return {
            "total": len(queue),
            "completed": sum(1 for item in queue if item["status"] == "completed"),
            "followUps": sum(1 for item in queue if item["status"] in {"follow_up_required", "incident"}),
        }

    def _list_visit_queue(self, cursor, worker_id: str, shift_date: date) -> list[dict[str, Any]]:
        cursor.execute(
            """
            select v.id::text,
                   v.scheduled_at,
                   v.purpose,
                   v.status,
                   coalesce(pf.display_name, trim(concat_ws(' ', p.first_name, p.last_name))) as patient_name,
                   coalesce(pf.preferred_language, cp.preferred_language, 'Language unknown') as preferred_language,
                   p.age
            from c3a_app_visits v
            join c3a_synthea_patients p on p.id = v.patient_id
            left join c3a_synthea_cald_profiles cp on cp.patient_id = p.id
            left join c3a_app_patient_profiles pf on pf.patient_id = p.id
            where v.worker_id = %s
              and v.scheduled_at::date = %s
            order by v.scheduled_at, v.sort_order
            """,
            (worker_id, shift_date),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "scheduledAt": _iso(row["scheduled_at"]),
                "patientName": row["patient_name"] or "Unknown patient",
                "patientMeta": f"{row['age']} yrs · {row['preferred_language']}",
                "purpose": row["purpose"],
                "status": row["status"],
            }
            for row in rows
        ]

    def _get_scenario(self, cursor, visit_id: str) -> dict[str, Any]:
        self._monitor_checklist_task_risks(cursor, visit_id)
        cursor.execute(
            """
            with visit_row as (
                select v.*,
                       w.name as worker_name,
                       w.role as worker_role,
                       coalesce(s.label, w.metadata->>'shift') as worker_shift
                from c3a_app_visits v
                join c3a_app_workers w on w.id = v.worker_id
                left join c3a_app_shifts s on s.id = v.shift_id
                where v.id = %s
            ),
            task_rows as (
                select t.*
                from c3a_app_care_tasks t
                where t.visit_id = %s
                order by t.sort_order, t.due_at
            ),
            event_rows as (
                select e.*
                from c3a_app_visit_events e
                where e.visit_id = %s
                order by e.occurred_at desc, e.created_at desc
            ),
            alert_rows as (
                select a.*
                from c3a_app_risk_alerts a
                where a.visit_id = %s
                order by case a.status when 'active' then 0 when 'acknowledged' then 1 else 2 end,
                         case a.level when 'high' then 0 when 'moderate' then 1 else 2 end,
                         a.updated_at desc
            ),
            snapshot_rows as (
                select ls.*
                from c3a_app_location_snapshots ls
                where ls.visit_id = %s
            ),
            medication_support_row as (
                select ms.*
                from c3a_app_medication_support_records ms
                where ms.visit_id = %s
            )
            select v.id::text,
                   v.patient_id::text,
                   v.worker_id,
                   v.worker_name,
                   v.worker_role,
                   v.worker_shift,
                   v.scheduled_at,
                   v.arrived_at,
                   v.location,
                   v.planned_address,
                   v.planned_lat,
                   v.planned_lon,
                   v.location_threshold_meters,
                   v.status,
                   v.lifecycle_step,
                   p.id::text as patient_id_text,
                   p.age,
                   p.gender,
                   p.first_name,
                   p.last_name,
                   cp.preferred_language,
                   cp.interpreter_required,
                   cp.cultural_background,
                   cp.mobility_support,
                   cp.cognitive_status,
                   cp.dietary_notes,
                   cp.communication_notes,
                   cp.care_risk_flags,
                   pf.display_name,
                   pf.medical_record_number,
                   pf.diagnosis_summary,
                   pf.notes,
                   pf.preferred_language as profile_preferred_language,
                   pf.interpreter_required as profile_interpreter_required,
                   pf.cultural_background as profile_cultural_background,
                   pf.mobility_support as profile_mobility_support,
                   pf.cognitive_status as profile_cognitive_status,
                   pf.dietary_notes as profile_dietary_notes,
                   pf.communication_notes as profile_communication_notes,
                   pf.care_risk_flags as profile_care_risk_flags,
                   pf.allergies_override,
                   pf.medications_override,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_allergies a
                           where a.patient_id = p.id
                           order by description
                           limit 8
                       ) a
                   ) as allergies,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_medications m
                           where m.patient_id = p.id
                           order by coalesce(m.stop_at, m.start_at) desc nulls last, description
                           limit 8
                       ) m
                   ) as medications,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_conditions c
                           where c.patient_id = p.id
                           order by coalesce(c.stop_date, c.start_date) desc nulls last, description
                           limit 8
                       ) c
                   ) as conditions,
                   coalesce(
                       (
                           select jsonb_agg(
                               jsonb_strip_nulls(
                                   jsonb_build_object(
                                       'id', t.id::text,
                                       'label', t.label,
                                       'type', t.type,
                                       'status', t.status,
                                       'dueAt', to_char(t.due_at, 'HH24:MI'),
                                       'detail', t.detail,
                                       'note', t.status_note
                                   )
                               )
                           )
                           from task_rows t
                       ),
                       '[]'::jsonb
                   ) as tasks,
                   coalesce(
                       (
                           select jsonb_agg(
                               jsonb_strip_nulls(
                                   jsonb_build_object(
                                       'id', e.id::text,
                                       'type', e.type,
                                       'timestamp', to_jsonb(e.occurred_at),
                                       'note', e.note
                                   )
                               )
                           )
                           from event_rows e
                       ),
                       '[]'::jsonb
                   ) as events,
                   coalesce(
                       (
                           select jsonb_agg(
                               jsonb_build_object(
                                   'id', a.id::text,
                                   'alertKey', a.alert_key,
                                   'riskType', coalesce(a.payload->>'risk_type', a.alert_key),
                                   'level', a.level,
                                   'title', a.title,
                                   'message', a.message,
                                   'source', a.source,
                                   'status', a.status,
                                   'visitId', a.visit_id::text,
                                   'assignedWorkerId', v.worker_id,
                                   'generatedFromEventId', a.generated_from_event_id::text,
                                   'details', a.payload,
                                   'createdAt', to_jsonb(a.created_at),
                                   'updatedAt', to_jsonb(a.updated_at),
                                   'acknowledgedAt', to_jsonb(a.acknowledged_at),
                                   'acknowledgedByWorkerId', a.acknowledged_by_worker_id,
                                   'resolvedAt', to_jsonb(a.resolved_at),
                                   'resolvedByWorkerId', a.resolved_by_worker_id,
                                   'dismissedAt', to_jsonb(a.dismissed_at),
                                   'dismissedByWorkerId', a.dismissed_by_worker_id,
                                   'reviewNote', a.review_note
                               )
                           )
                           from alert_rows a
                       ),
                       '[]'::jsonb
                   ) as alerts,
                   coalesce(
                       (
                           select jsonb_object_agg(
                               ls.type,
                               jsonb_strip_nulls(
                                   jsonb_build_object(
                                       'id', ls.id::text,
                                       'type', ls.type,
                                       'timestamp', to_jsonb(ls.recorded_at),
                                       'coords',
                                           case
                                               when ls.lat is null or ls.lon is null then null
                                               else jsonb_build_object(
                                                   'latitude', ls.lat::float8,
                                                   'longitude', ls.lon::float8
                                               )
                                           end,
                                       'accuracyMeters', ls.accuracy_meters::float8,
                                       'distanceFromPlannedMeters', ls.distance_from_planned_meters::float8,
                                       'withinExpectedArea', ls.within_expected_area,
                                       'permissionStatus', ls.permission_status,
                                       'source', ls.source,
                                       'note', ls.note
                                   )
                               )
                           )
                           from snapshot_rows ls
                       ),
                       '{}'::jsonb
                   ) as snapshots,
                   (
                       select jsonb_strip_nulls(
                           jsonb_build_object(
                               'id', ms.id::text,
                               'visitId', ms.visit_id::text,
                               'taskId', ms.task_id::text,
                               'status', ms.status,
                               'notes', ms.notes,
                               'timestamp', to_jsonb(ms.recorded_at),
                               'hcwId', ms.hcw_id,
                               'medicationNames', ms.medication_names,
                               'medicationItems', ms.medication_items
                           )
                       )
                       from medication_support_row ms
                   ) as medication_support
            from visit_row v
            join c3a_synthea_patients p on p.id = v.patient_id
            left join c3a_synthea_cald_profiles cp on cp.patient_id = p.id
            left join c3a_app_patient_profiles pf on pf.patient_id = p.id
            """,
            (visit_id, visit_id, visit_id, visit_id, visit_id, visit_id),
        )
        row = cursor.fetchone()
        if not row:
            raise VisitNotFoundError(f"Visit {visit_id} was not found")
        name = row["display_name"] or " ".join(part for part in [row["first_name"], row["last_name"]] if part) or "Unknown patient"
        diagnosis = row["diagnosis_summary"] or _first_or_join(row["conditions"])
        patient = _strip_none(
            {
                "id": row["patient_id_text"],
                "name": name,
                "age": row["age"],
                "gender": row["gender"],
                "medicalRecordNumber": row["medical_record_number"] or row["patient_id_text"][:8],
                "diagnosis": diagnosis,
                "notes": row["notes"],
                "preferredLanguage": row["profile_preferred_language"] or row["preferred_language"],
                "interpreterRequired": _coalesce_bool(row["profile_interpreter_required"], row["interpreter_required"]),
                "culturalBackground": row["profile_cultural_background"] or row["cultural_background"],
                "mobilitySupport": row["profile_mobility_support"] or row["mobility_support"],
                "cognitiveStatus": row["profile_cognitive_status"] or row["cognitive_status"],
                "dietaryNotes": row["profile_dietary_notes"] or row["dietary_notes"],
                "communicationNotes": row["profile_communication_notes"] or row["communication_notes"],
                "careRiskFlags": _list_or_default(row["profile_care_risk_flags"], row["care_risk_flags"]),
                "allergies": _list_or_default(row["allergies_override"], row["allergies"]),
                "medications": _list_or_default(row["medications_override"], row["medications"]),
                "pastMedicalHistory": _first_or_join(row["conditions"]),
            }
        )
        worker = {
            "id": row["worker_id"],
            "name": row["worker_name"],
            "role": row["worker_role"],
            "shift": row["worker_shift"] or "Assigned visits",
        }
        tasks = list(row["tasks"] or [])
        events = [_normalise_timestamp_item(item) for item in (row["events"] or [])]
        alerts = list(row["alerts"] or [])
        snapshots = {
            key: _normalise_timestamp_item(value)
            for key, value in (row["snapshots"] or {}).items()
        }
        medication_support = (
            _normalise_timestamp_item(row["medication_support"])
            if row["medication_support"]
            else None
        )
        visit_context = {
            "id": row["id"],
            "patientId": row["patient_id"],
            "scheduledAt": _iso(row["scheduled_at"]),
            "arrivedAt": _iso_or_none(row["arrived_at"]),
            "location": row["location"],
            "plannedAddress": row["planned_address"],
            "plannedCoords": _coords(row["planned_lat"], row["planned_lon"]),
            "locationThresholdMeters": _float_or_none(row["location_threshold_meters"]),
            "checkIn": snapshots.get("check_in"),
            "checkOut": snapshots.get("check_out"),
            "status": row["status"],
        }
        return {
            "worker": worker,
            "patient": patient,
            "visit": {key: value for key, value in visit_context.items() if value is not None},
            "lifecycleStep": row["lifecycle_step"],
            "tasks": tasks,
            "medicationSupport": medication_support,
            "events": events,
            "alerts": alerts,
            "incidentChecklist": _incident_checklist(events),
        }

    def _visit_row(self, cursor, visit_id: str):
        cursor.execute("select * from c3a_app_visits where id = %s", (visit_id,))
        return cursor.fetchone()

    def _visit_row_for_update(self, cursor, visit_id: str):
        cursor.execute("select * from c3a_app_visits where id = %s for update", (visit_id,))
        row = cursor.fetchone()
        if not row:
            raise VisitNotFoundError(f"Visit {visit_id} was not found")
        return row

    def _task_row_for_update(self, cursor, visit_id: str, task_id: str):
        cursor.execute("select * from c3a_app_care_tasks where visit_id = %s and id = %s for update", (visit_id, task_id))
        row = cursor.fetchone()
        if not row:
            raise VisitNotFoundError(f"Task {task_id} was not found for visit {visit_id}")
        return row

    def _task_id_by_key(self, cursor, visit_id: str, key: str):
        cursor.execute("select id from c3a_app_care_tasks where visit_id = %s and task_key = %s", (visit_id, key))
        row = cursor.fetchone()
        return row["id"] if row else None

    def _task_type(self, cursor, task_id: str) -> str | None:
        cursor.execute("select type from c3a_app_care_tasks where id = %s", (task_id,))
        row = cursor.fetchone()
        return row["type"] if row else None

    def _patient_medications_for_visit(self, cursor, visit_id: str) -> list[str]:
        cursor.execute(
            """
            select coalesce(
                       pf.medications_override,
                       (
                           select jsonb_agg(description order by description)
                           from (
                               select description
                               from c3a_synthea_medications m
                               where m.patient_id = v.patient_id
                               order by coalesce(m.stop_at, m.start_at) desc nulls last, description
                               limit 8
                           ) meds
                       ),
                       '[]'::jsonb
                   ) as medications
            from c3a_app_visits v
            left join c3a_app_patient_profiles pf on pf.patient_id = v.patient_id
            where v.id = %s
            """,
            (visit_id,),
        )
        row = cursor.fetchone()
        return _list_or_default(row["medications"] if row else [], [])

    def _latest_visit_for_patient(self, cursor, patient_id: str) -> str | None:
        cursor.execute(
            """
            select id::text
            from c3a_app_visits
            where patient_id = %s
            order by scheduled_at desc
            limit 1
            """,
            (patient_id,),
        )
        row = cursor.fetchone()
        return row["id"] if row else None

    def _patient_context(self, cursor, patient_id: UUID) -> dict[str, Any]:
        cursor.execute(
            """
            select p.id::text,
                   p.age,
                   p.gender,
                   p.first_name,
                   p.last_name,
                   cp.preferred_language,
                   cp.interpreter_required,
                   cp.cultural_background,
                   cp.mobility_support,
                   cp.cognitive_status,
                   cp.dietary_notes,
                   cp.communication_notes,
                   cp.care_risk_flags,
                   pf.display_name,
                   pf.medical_record_number,
                   pf.diagnosis_summary,
                   pf.notes,
                   pf.preferred_language as profile_preferred_language,
                   pf.interpreter_required as profile_interpreter_required,
                   pf.cultural_background as profile_cultural_background,
                   pf.mobility_support as profile_mobility_support,
                   pf.cognitive_status as profile_cognitive_status,
                   pf.dietary_notes as profile_dietary_notes,
                   pf.communication_notes as profile_communication_notes,
                   pf.care_risk_flags as profile_care_risk_flags,
                   pf.allergies_override,
                   pf.medications_override,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_allergies a
                           where a.patient_id = p.id
                           order by description
                           limit 8
                       ) a
                   ) as allergies,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_medications m
                           where m.patient_id = p.id
                           order by coalesce(m.stop_at, m.start_at) desc nulls last, description
                           limit 8
                       ) m
                   ) as medications,
                   (
                       select jsonb_agg(description order by description)
                       from (
                           select description
                           from c3a_synthea_conditions c
                           where c.patient_id = p.id
                           order by coalesce(c.stop_date, c.start_date) desc nulls last, description
                           limit 8
                       ) c
                   ) as conditions
            from c3a_synthea_patients p
            left join c3a_synthea_cald_profiles cp on cp.patient_id = p.id
            left join c3a_app_patient_profiles pf on pf.patient_id = p.id
            where p.id = %s
            """,
            (patient_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise VisitNotFoundError(f"Patient {patient_id} was not found")
        name = row["display_name"] or " ".join(part for part in [row["first_name"], row["last_name"]] if part) or "Unknown patient"
        diagnosis = row["diagnosis_summary"] or _first_or_join(row["conditions"])
        return _strip_none(
            {
                "id": row["id"],
                "name": name,
                "age": row["age"],
                "gender": row["gender"],
                "medicalRecordNumber": row["medical_record_number"] or row["id"][:8],
                "diagnosis": diagnosis,
                "notes": row["notes"],
                "preferredLanguage": row["profile_preferred_language"] or row["preferred_language"],
                "interpreterRequired": _coalesce_bool(row["profile_interpreter_required"], row["interpreter_required"]),
                "culturalBackground": row["profile_cultural_background"] or row["cultural_background"],
                "mobilitySupport": row["profile_mobility_support"] or row["mobility_support"],
                "cognitiveStatus": row["profile_cognitive_status"] or row["cognitive_status"],
                "dietaryNotes": row["profile_dietary_notes"] or row["dietary_notes"],
                "communicationNotes": row["profile_communication_notes"] or row["communication_notes"],
                "careRiskFlags": _list_or_default(row["profile_care_risk_flags"], row["care_risk_flags"]),
                "allergies": _list_or_default(row["allergies_override"], row["allergies"]),
                "medications": _list_or_default(row["medications_override"], row["medications"]),
                "pastMedicalHistory": _first_or_join(row["conditions"]),
            }
        )

    def _worker_context(self, cursor, worker_id: str) -> dict[str, Any]:
        cursor.execute(
            """
            select w.id, w.name, w.role, coalesce(s.label, w.metadata->>'shift') as shift
            from c3a_app_workers w
            left join c3a_app_shifts s on s.worker_id = w.id
            where w.id = %s
            order by s.shift_date desc nulls last
            limit 1
            """,
            (worker_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {"id": worker_id, "name": worker_id, "role": "care_worker", "shift": "Assigned visits"}
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "shift": row["shift"] or "Assigned visits",
        }

    def _tasks(self, cursor, visit_id: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            select id::text, task_key, label, type, status, due_at, detail
            from c3a_app_care_tasks
            where visit_id = %s
            order by sort_order, due_at
            """,
            (visit_id,),
        )
        return [
            _strip_none(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "type": row["type"],
                    "status": row["status"],
                    "dueAt": _time_label(row["due_at"]),
                    "detail": row["detail"],
                }
            )
            for row in cursor.fetchall()
        ]

    def _events(self, cursor, visit_id: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            select id::text, type, occurred_at, note
            from c3a_app_visit_events
            where visit_id = %s
            order by occurred_at desc, created_at desc
            """,
            (visit_id,),
        )
        return [
            _strip_none(
                {
                    "id": row["id"],
                    "type": row["type"],
                    "timestamp": _iso(row["occurred_at"]),
                    "note": row["note"],
                }
            )
            for row in cursor.fetchall()
        ]

    def _alerts(self, cursor, visit_id: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            select id::text, alert_key, level, title, message, source, status,
                   generated_from_event_id::text, payload, created_at, updated_at,
                   acknowledged_at, acknowledged_by_worker_id,
                   resolved_at, resolved_by_worker_id,
                   dismissed_at, dismissed_by_worker_id, review_note
            from c3a_app_risk_alerts
            where visit_id = %s
            order by case status when 'active' then 0 when 'acknowledged' then 1 else 2 end,
                     case level when 'high' then 0 when 'moderate' then 1 else 2 end,
                     updated_at desc
            """,
            (visit_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def _location_snapshots(self, cursor, visit_id: str) -> dict[str, dict[str, Any]]:
        cursor.execute(
            """
            select id::text,
                   type,
                   recorded_at,
                   lat,
                   lon,
                   accuracy_meters,
                   distance_from_planned_meters,
                   within_expected_area,
                   permission_status,
                   source,
                   note
            from c3a_app_location_snapshots
            where visit_id = %s
            """,
            (visit_id,),
        )
        snapshots = {}
        for row in cursor.fetchall():
            snapshots[row["type"]] = _strip_none(
                {
                    "id": row["id"],
                    "type": row["type"],
                    "timestamp": _iso(row["recorded_at"]),
                    "coords": _coords(row["lat"], row["lon"]),
                    "accuracyMeters": _float_or_none(row["accuracy_meters"]),
                    "distanceFromPlannedMeters": _float_or_none(row["distance_from_planned_meters"]),
                    "withinExpectedArea": row["within_expected_area"],
                    "permissionStatus": row["permission_status"],
                    "source": row["source"],
                    "note": row["note"],
                }
            )
        return snapshots

    def _upsert_location_snapshot(self, cursor, visit_id: str, snapshot: dict[str, Any]) -> str:
        coords = snapshot.get("coords") or {}
        cursor.execute(
            """
            insert into c3a_app_location_snapshots (
                visit_id,
                type,
                recorded_at,
                lat,
                lon,
                accuracy_meters,
                distance_from_planned_meters,
                within_expected_area,
                permission_status,
                source,
                note,
                updated_at
            )
            values (
                %(visit_id)s,
                %(type)s,
                %(recorded_at)s,
                %(lat)s,
                %(lon)s,
                %(accuracy_meters)s,
                %(distance_from_planned_meters)s,
                %(within_expected_area)s,
                %(permission_status)s,
                %(source)s,
                %(note)s,
                now()
            )
            on conflict (visit_id, type) do update
            set recorded_at = excluded.recorded_at,
                lat = excluded.lat,
                lon = excluded.lon,
                accuracy_meters = excluded.accuracy_meters,
                distance_from_planned_meters = excluded.distance_from_planned_meters,
                within_expected_area = excluded.within_expected_area,
                permission_status = excluded.permission_status,
                source = excluded.source,
                note = excluded.note,
                updated_at = now()
            returning id
            """,
            {
                "visit_id": visit_id,
                "type": snapshot["type"],
                "recorded_at": snapshot.get("timestamp") or datetime.now(timezone.utc),
                "lat": coords.get("latitude"),
                "lon": coords.get("longitude"),
                "accuracy_meters": snapshot.get("accuracyMeters"),
                "distance_from_planned_meters": snapshot.get("distanceFromPlannedMeters"),
                "within_expected_area": snapshot.get("withinExpectedArea"),
                "permission_status": snapshot.get("permissionStatus") or "unknown",
                "source": snapshot.get("source") or "manual_override",
                "note": snapshot.get("note"),
            },
        )
        return cursor.fetchone()["id"]

    def _insert_event(
        self,
        cursor,
        visit_id: str,
        event_type: str,
        worker_id: str | None,
        task_id: str | None = None,
        location_snapshot_id: str | None = None,
        note: str | None = None,
    ) -> str:
        cursor.execute(
            """
            insert into c3a_app_visit_events (
                visit_id,
                task_id,
                location_snapshot_id,
                created_by_worker_id,
                type,
                note
            )
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (visit_id, task_id, location_snapshot_id, worker_id, event_type, note),
        )
        return cursor.fetchone()["id"]

    def _event_exists(self, cursor, visit_id: str, event_type: str) -> bool:
        cursor.execute(
            "select 1 from c3a_app_visit_events where visit_id = %s and type = %s limit 1",
            (visit_id, event_type),
        )
        return cursor.fetchone() is not None

    def _upsert_alert(self, cursor, visit_id: str, alert: dict[str, Any], event_id: str | None) -> None:
        cursor.execute(
            """
            insert into c3a_app_risk_alerts (
                visit_id,
                alert_key,
                level,
                title,
                message,
                source,
                generated_from_event_id,
                payload,
                updated_at
            )
            values (%s, %s, %s, %s, %s, 'rules', %s, %s::jsonb, now())
            on conflict (visit_id, alert_key) do update
            set level = excluded.level,
                title = excluded.title,
                message = excluded.message,
                source = excluded.source,
                status = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.status
                    else 'active'
                end,
                acknowledged_at = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.acknowledged_at
                    else null
                end,
                acknowledged_by_worker_id = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.acknowledged_by_worker_id
                    else null
                end,
                resolved_at = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.resolved_at
                    else null
                end,
                resolved_by_worker_id = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.resolved_by_worker_id
                    else null
                end,
                dismissed_at = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.dismissed_at
                    else null
                end,
                dismissed_by_worker_id = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.dismissed_by_worker_id
                    else null
                end,
                review_note = case
                    when c3a_app_risk_alerts.payload = excluded.payload
                        then c3a_app_risk_alerts.review_note
                    else null
                end,
                generated_from_event_id = excluded.generated_from_event_id,
                payload = excluded.payload,
                updated_at = now()
            """,
            (
                visit_id,
                alert["alert_key"],
                alert["level"],
                alert["title"],
                alert["message"],
                event_id,
                json.dumps(alert.get("payload", {})),
            ),
        )

    def _sync_location_alert(
        self,
        cursor,
        visit_id: str,
        snapshot: dict[str, Any],
        event_id: str | None,
    ) -> None:
        alert = location_alert(snapshot)
        if alert:
            self._upsert_alert(cursor, visit_id, alert, event_id)
            return
        if snapshot.get("withinExpectedArea") is True:
            cursor.execute(
                """
                update c3a_app_risk_alerts
                set status = 'resolved',
                    resolved_at = now(),
                    resolved_by_worker_id = null,
                    updated_at = now()
                where visit_id = %s
                  and alert_key = %s
                  and status in ('active', 'acknowledged')
                """,
                (visit_id, LOCATION_ALERT_KEY),
            )

    def _assert_visit_access(
        self,
        cursor,
        visit_id: str,
        worker_id: str | None,
        requested_role: str | None = None,
    ) -> None:
        if not worker_id:
            raise VisitValidationError("workerId is required for visit access")
        cursor.execute(
            """
            select w.role, w.active, v.worker_id as assigned_worker_id
            from c3a_app_workers w
            cross join c3a_app_visits v
            where w.id = %s and v.id = %s
            """,
            (worker_id, visit_id),
        )
        access = cursor.fetchone()
        if not access:
            raise VisitNotFoundError("Worker or visit was not found")
        if not access["active"] or (requested_role and access["role"] != requested_role):
            raise VisitAccessError("Worker role is invalid or inactive")
        if access["role"] != "supervisor" and access["assigned_worker_id"] != worker_id:
            raise VisitAccessError("Worker is not assigned to this visit")

    def _monitor_checklist_task_risks(self, cursor, visit_id: str) -> None:
        cursor.execute(
            """
            select id::text, label, type, status, due_at
            from c3a_app_care_tasks
            where visit_id = %s
            order by sort_order, due_at
            """,
            (visit_id,),
        )
        tasks = cursor.fetchall()
        active_alert_keys: list[str] = []
        for task in tasks:
            alert = evaluate_checklist_task(task)
            if alert is None:
                continue
            active_alert_keys.append(alert["alert_key"])
            self._upsert_alert(cursor, visit_id, alert, None)

        cursor.execute(
            """
            update c3a_app_risk_alerts
            set status = 'resolved',
                resolved_at = now(),
                resolved_by_worker_id = null,
                updated_at = now()
            where visit_id = %s
              and alert_key like %s
              and status in ('active', 'acknowledged')
              and not (alert_key = any(%s))
            """,
            (visit_id, f"{CHECKLIST_ALERT_KEY_PREFIX}%", active_alert_keys),
        )


def _issue_mapping(task: dict[str, Any], issue_type: str):
    if issue_type == "safety_concern":
        return (
            "patient_unsteady",
            "issue",
            "incident",
            "incident_active",
            {
                "alert_key": f"unsteady-risk-{task['id']}",
                "level": "high",
                "title": "Patient appears unsteady",
                "message": "Pause routine tasks, complete mobility observations, and consider a later follow-up or escalation.",
            },
        )
    if issue_type == "patient_declined" and task["type"] != "medication":
        return (
            "follow_up_required",
            "skipped",
            "follow_up_required",
            "review",
            {
                "alert_key": f"follow-up-{task['id']}",
                "level": "moderate",
                "title": "Follow-up required",
                "message": "Schedule a later check and include the reason in the visit summary.",
            },
        )
    if task["type"] == "medication":
        support_status, task_status = {
            "medication_delayed": ("Delayed", "delayed"),
            "medication_unavailable": ("Unavailable", "issue"),
            "medication_unable_to_confirm": ("Unable to Confirm", "issue"),
            "patient_declined": ("Declined", "skipped"),
        }.get(issue_type, ("Delayed", "delayed"))
        decision = evaluate_medication_support(
            support_status,
            current_visit_status="in_progress",
            current_lifecycle_step="care_tasks",
        )
        alert = dict(decision["alert"])
        alert["alert_key"] = f"{decision['event_type']}-{task['id']}"
        return (
            decision["event_type"],
            task_status,
            decision["visit_status"],
            decision["lifecycle_step"],
            alert,
        )
    return (
        "follow_up_required",
        "issue",
        "follow_up_required",
        "review",
        {
            "alert_key": f"follow-up-{task['id']}",
            "level": "moderate",
            "title": "Follow-up required",
            "message": "Schedule a later check and include the reason in the visit summary.",
        },
    )


def _issue_note(task: dict[str, Any], issue_type: str) -> str:
    if issue_type == "patient_declined":
        return f"{task['label']}: patient declined"
    if issue_type == "safety_concern":
        return f"{task['label']}: safety concern"
    if issue_type.startswith("medication_"):
        return f"{task['label']}: {issue_type.replace('_', ' ')}"
    return f"{task['label']}: could not complete"


def _normalise_medication_items(items: Any, medication_names: list[str]) -> list[dict[str, str]]:
    by_name = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            taken_status = str(item.get("takenStatus") or "").strip()
            taken_at = str(item.get("takenAt") or "").strip()
            if name:
                by_name[name] = {
                    "takenStatus": taken_status,
                    "takenAt": taken_at,
                }

    result = []
    for name in medication_names:
        clean_name = str(name).strip()
        if not clean_name:
            continue
        existing = by_name.get(clean_name, {})
        taken_status = existing.get("takenStatus", "")
        if taken_status not in MEDICATION_TAKEN_STATUSES:
            raise VisitValidationError(f"Medication taken status is required for {clean_name}")
        normalised_item = {"name": clean_name, "takenStatus": taken_status}
        if taken_status == "Taken":
            normalised_item["takenAt"] = existing.get("takenAt") or datetime.now(timezone.utc).isoformat()
        result.append(normalised_item)

    if not result:
        raise VisitValidationError("At least one medication must be listed for medication support")
    return result


def _derive_location_snapshot(
    snapshot: dict[str, Any],
    visit: dict[str, Any],
    snapshot_type: str,
) -> dict[str, Any]:
    return derive_location_snapshot(
        snapshot,
        snapshot_type=snapshot_type,
        planned_latitude=visit.get("planned_lat"),
        planned_longitude=visit.get("planned_lon"),
        threshold_meters=visit.get("location_threshold_meters"),
    )


def _incident_checklist(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = {event.get("note") for event in events if event.get("type") == "incident_check_completed"}
    return [
        {"id": "consciousness", "label": "Check consciousness and breathing", "completed": "consciousness" in completed},
        {"id": "pain", "label": "Ask about pain, dizziness, and head impact", "completed": "pain" in completed},
        {"id": "injury", "label": "Look for visible injury without moving the patient unnecessarily", "completed": "injury" in completed},
        {"id": "supervisor", "label": "Contact supervisor or emergency support according to policy", "completed": "supervisor" in completed},
        {"id": "document", "label": "Record incident note and schedule follow-up", "completed": "document" in completed},
    ]


def _json_array(value: Any) -> str:
    import json

    if value is None:
        value = []
    return json.dumps(value)


def _json_array_or_none(value: Any) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value)


def _strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _iso(value: datetime) -> str:
    return value.isoformat()


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _coords(lat: Any, lon: Any) -> dict[str, float] | None:
    if lat is None or lon is None:
        return None
    return {"latitude": float(lat), "longitude": float(lon)}


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None


def _time_label(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%H:%M")


def _list_or_default(primary: Any, fallback: Any) -> list[str]:
    value = primary if primary not in (None, []) else fallback
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _first_or_join(value: Any) -> str | None:
    items = _list_or_default(value, [])
    if not items:
        return None
    return "; ".join(items[:3])


def _coalesce_bool(primary: Any, fallback: Any) -> bool | None:
    return primary if primary is not None else fallback


def _normalise_timestamp_item(item: dict[str, Any]) -> dict[str, Any]:
    value = dict(item)
    timestamp = value.get("timestamp")
    if hasattr(timestamp, "isoformat"):
        value["timestamp"] = timestamp.isoformat()
    return value
