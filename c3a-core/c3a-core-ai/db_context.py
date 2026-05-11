"""PostgreSQL context retrieval for synthetic Synthea patient data."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

PATIENT_TERMS = {
    "patient",
    "patients",
    "resident",
    "elderly",
    "demographic",
    "demographics",
    "profile",
    "profiles",
    "age",
    "gender",
    "race",
    "ethnicity",
    "address",
    "income",
}
PATIENT_PHRASES = {"older adult", "older adults"}

CALD_TERMS = {
    "cald",
    "cultural",
    "culture",
    "language",
    "languages",
    "interpreter",
    "religion",
    "religious",
    "dietary",
    "communication",
    "mobility",
    "cognitive",
}
CALD_PHRASES = {"care risk", "care risks", "health literacy"}

CONDITION_TERMS = {"condition", "conditions", "diagnosis", "diagnoses", "problem", "problems"}
CONDITION_PHRASES = {"medical history"}

MEDICATION_TERMS = {
    "medication",
    "medications",
    "medicine",
    "medicines",
    "drug",
    "drugs",
    "prescription",
    "prescriptions",
}

ALLERGY_TERMS = {"allergy", "allergies", "allergic"}
ENCOUNTER_TERMS = {"encounter", "encounters", "visit", "visits", "admission", "admissions"}

OBSERVATION_TERMS = {
    "observation",
    "observations",
    "vital",
    "vitals",
    "lab",
    "labs",
    "laboratory",
    "bmi",
    "glucose",
    "cholesterol",
    "creatinine",
    "pain",
}
OBSERVATION_PHRASES = {"blood pressure", "oxygen saturation"}

OBSERVATION_PRIORITY = (
    "Systolic Blood Pressure",
    "Diastolic Blood Pressure",
    "Heart rate",
    "Respiratory rate",
    "Body temperature",
    "Oxygen saturation in Arterial blood",
    "Body Weight",
    "Body Mass Index",
    "Body mass index (BMI) [Ratio]",
    "Pain severity - 0-10 verbal numeric rating [Score] - Reported",
    "Glucose",
    "Hemoglobin A1c/Hemoglobin.total in Blood",
    "Total Cholesterol",
    "Low Density Lipoprotein Cholesterol",
    "High Density Lipoprotein Cholesterol",
    "Triglycerides",
    "Creatinine",
    "Estimated Glomerular Filtration Rate",
)


@dataclass(frozen=True)
class DbContextResult:
    context: str
    metadata: dict[str, Any]


class DbContextRetriever:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.enabled = _env_bool("CHAT_DB_CONTEXT_ENABLED", True)
        self.max_patients = _env_int("CHAT_DB_CONTEXT_MAX_PATIENTS", 6)
        self.max_rows_per_table = _env_int("CHAT_DB_CONTEXT_MAX_ROWS_PER_TABLE", 8)
        self._last_error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.database_url)

    def status(self) -> dict[str, Any]:
        status = "configured" if self.enabled and self.configured else "unavailable"
        if not self.enabled:
            status = "disabled"
        if self._last_error:
            status = "unavailable"
        return {
            "status": status,
            "enabled": self.enabled,
            "database_url_configured": self.configured,
            "max_patients": self.max_patients,
            "max_rows_per_table": self.max_rows_per_table,
            "last_error": self._last_error,
        }

    async def retrieve(self, query: str, patient_context: Any = None) -> DbContextResult:
        metadata = {
            "enabled_for_chat": self.enabled,
            "used_for_chat": False,
            "configured": self.configured,
            "matched_intents": [],
            "tables": [],
            "result_counts": {},
            "status": self.status(),
        }
        if not self.enabled or not query.strip():
            return DbContextResult(context="", metadata=metadata)
        if not self.configured:
            metadata["status"] = self.status()
            return DbContextResult(context="", metadata=metadata)

        intents = _matched_intents(query)
        patient_id = _patient_id_from_context(patient_context) or _patient_id_from_query(query)
        if patient_id and not intents:
            intents = ["patients", "cald_profiles", "conditions", "medications", "allergies", "encounters", "observations"]
        if not intents:
            return DbContextResult(context="", metadata=metadata)

        started_at = time.perf_counter()
        try:
            result = await asyncio.to_thread(self._retrieve_sync, query, patient_id, intents)
            self._last_error = None
            result.metadata["status"] = self.status()
            logger.info(
                "PostgreSQL context retrieval completed intents=%s tables=%s elapsed_ms=%.1f",
                result.metadata["matched_intents"],
                result.metadata["tables"],
                (time.perf_counter() - started_at) * 1000,
            )
            return result
        except Exception as exc:
            self._last_error = _safe_error_message(exc, self.database_url)
            logger.warning(
                "PostgreSQL context retrieval failed elapsed_ms=%.1f error=%s",
                (time.perf_counter() - started_at) * 1000,
                self._last_error,
                exc_info=True,
            )
            metadata["status"] = self.status()
            return DbContextResult(context="", metadata=metadata)

    def _retrieve_sync(self, query: str, patient_id: str | None, intents: list[str]) -> DbContextResult:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                patient_rows = _find_patients(cursor, query, patient_id, self.max_patients)
                patient_ids = [str(row["id"]) for row in patient_rows]
                if patient_id and patient_id not in patient_ids:
                    patient_ids = [patient_id]

                sections: list[str] = []
                tables: list[str] = []
                counts: dict[str, int] = {}

                if "patients" in intents or patient_rows:
                    if not patient_rows and ("patients" in intents or any(intent in intents for intent in _clinical_intents())):
                        patient_rows = _sample_patients(cursor, self.max_patients)
                        patient_ids = [str(row["id"]) for row in patient_rows]
                    _add_section(sections, "Patients", _format_patients(patient_rows))
                    tables.append("c3a_synthea_patients")
                    counts["patients"] = len(patient_rows)

                if "cald_profiles" in intents:
                    distribution_rows = _cald_distribution(cursor)
                    if distribution_rows:
                        _add_section(sections, "CALD Distribution", _format_cald_distribution(distribution_rows))
                    rows = _cald_profiles(cursor, patient_ids, self.max_patients)
                    if rows:
                        _add_section(sections, "CALD Profiles", _format_cald_profiles(rows))
                    else:
                        _add_section(sections, "CALD Profiles", "No matching CALD profile rows were found.")
                    tables.append("c3a_synthea_cald_profiles")
                    counts["cald_profiles"] = len(rows)
                    counts["cald_distribution"] = len(distribution_rows)

                if "conditions" in intents:
                    rows = _rows_for_patients(cursor, "conditions", patient_ids, self.max_rows_per_table)
                    _add_section(sections, "Conditions", _format_conditions(rows) or "No matching condition rows were found.")
                    tables.append("c3a_synthea_conditions")
                    counts["conditions"] = len(rows)

                if "medications" in intents:
                    rows = _rows_for_patients(cursor, "medications", patient_ids, self.max_rows_per_table)
                    _add_section(sections, "Medications", _format_medications(rows) or "No matching medication rows were found.")
                    tables.append("c3a_synthea_medications")
                    counts["medications"] = len(rows)

                if "allergies" in intents:
                    rows = _rows_for_patients(cursor, "allergies", patient_ids, self.max_rows_per_table)
                    _add_section(sections, "Allergies", _format_allergies(rows) or "No matching allergy rows were found.")
                    tables.append("c3a_synthea_allergies")
                    counts["allergies"] = len(rows)

                if "encounters" in intents:
                    rows = _rows_for_patients(cursor, "encounters", patient_ids, self.max_rows_per_table)
                    _add_section(sections, "Encounters", _format_encounters(rows) or "No matching encounter rows were found.")
                    tables.append("c3a_synthea_encounters")
                    counts["encounters"] = len(rows)

                if "observations" in intents:
                    rows = _observations(cursor, patient_ids, self.max_rows_per_table)
                    _add_section(sections, "Observations", _format_observations(rows) or "No matching observation rows were found.")
                    tables.append("c3a_synthea_observations")
                    counts["observations"] = len(rows)

        context = _build_context(sections) if sections else ""
        return DbContextResult(
            context=context,
            metadata={
                "enabled_for_chat": self.enabled,
                "used_for_chat": bool(context),
                "configured": self.configured,
                "matched_intents": intents,
                "tables": tables,
                "result_counts": counts,
                "status": self.status(),
            },
        )


def _matched_intents(query: str) -> list[str]:
    lowered = query.lower()
    words = set(re.findall(r"[a-z][a-z-]*", lowered))
    intents: list[str] = []
    if _has_any(words, lowered, PATIENT_TERMS, PATIENT_PHRASES):
        intents.append("patients")
    if _has_any(words, lowered, CALD_TERMS, CALD_PHRASES):
        intents.append("cald_profiles")
    if _has_any(words, lowered, CONDITION_TERMS, CONDITION_PHRASES):
        intents.append("conditions")
    if _has_any(words, lowered, MEDICATION_TERMS, set()):
        intents.append("medications")
    if _has_any(words, lowered, ALLERGY_TERMS, set()):
        intents.append("allergies")
    if _has_any(words, lowered, ENCOUNTER_TERMS, set()):
        intents.append("encounters")
    if _has_any(words, lowered, OBSERVATION_TERMS, OBSERVATION_PHRASES):
        intents.append("observations")

    if "cald_profiles" in intents and "patients" not in intents:
        intents.insert(0, "patients")
    if any(intent in intents for intent in _clinical_intents()) and "patients" not in intents:
        intents.insert(0, "patients")
    return intents


def _clinical_intents() -> set[str]:
    return {"conditions", "medications", "allergies", "encounters", "observations"}


def _has_any(words: set[str], lowered: str, terms: set[str], phrases: set[str]) -> bool:
    return bool(words & terms) or any(phrase in lowered for phrase in phrases)


def _patient_id_from_context(patient_context: Any) -> str | None:
    raw = getattr(patient_context, "id", None)
    return _normalise_uuid(raw)


def _patient_id_from_query(query: str) -> str | None:
    match = UUID_PATTERN.search(query)
    return _normalise_uuid(match.group(0)) if match else None


def _normalise_uuid(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _find_patients(cursor, query: str, patient_id: str | None, limit: int) -> list[dict[str, Any]]:
    if patient_id:
        cursor.execute(_PATIENT_SELECT + " WHERE p.id = %s LIMIT %s", (patient_id, limit))
        return list(cursor.fetchall())

    names = _name_terms(query)
    if names:
        patterns = [f"%{name}%" for name in names]
        cursor.execute(
            _PATIENT_SELECT
            + """
            WHERE EXISTS (
                SELECT 1 FROM unnest(%s::text[]) AS term
                WHERE p.first_name ILIKE term OR p.last_name ILIKE term
            )
            ORDER BY p.last_name, p.first_name
            LIMIT %s
            """,
            (patterns, limit),
        )
        rows = list(cursor.fetchall())
        if rows:
            return rows
    return []


def _sample_patients(cursor, limit: int) -> list[dict[str, Any]]:
    cursor.execute(_PATIENT_SELECT + " ORDER BY p.last_name, p.first_name LIMIT %s", (limit,))
    return list(cursor.fetchall())


def _name_terms(query: str) -> list[str]:
    stopwords = PATIENT_TERMS | CALD_TERMS | CONDITION_TERMS | MEDICATION_TERMS | ALLERGY_TERMS | ENCOUNTER_TERMS | OBSERVATION_TERMS
    stopwords |= {
        "and",
        "are",
        "data",
        "database",
        "dataset",
        "few",
        "for",
        "from",
        "general",
        "how",
        "record",
        "recorded",
        "records",
        "recent",
        "represented",
        "show",
        "synthea",
        "synthetic",
        "tell",
        "the",
        "what",
        "which",
        "with",
    }
    terms = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", query):
        lowered = term.lower()
        if lowered not in stopwords:
            terms.append(term)
    return terms[:4]


def _cald_profiles(cursor, patient_ids: list[str], limit: int) -> list[dict[str, Any]]:
    if patient_ids:
        cursor.execute(
            """
            SELECT c.*, p.first_name, p.last_name, p.age, p.gender
            FROM c3a_synthea_cald_profiles c
            JOIN c3a_synthea_patients p ON p.id = c.patient_id
            WHERE c.patient_id = ANY(%s::uuid[])
            ORDER BY p.last_name, p.first_name
            LIMIT %s
            """,
            (patient_ids, limit),
        )
    else:
        cursor.execute(
            """
            SELECT c.*, p.first_name, p.last_name, p.age, p.gender
            FROM c3a_synthea_cald_profiles c
            JOIN c3a_synthea_patients p ON p.id = c.patient_id
            ORDER BY c.preferred_language, p.last_name, p.first_name
            LIMIT %s
            """,
            (limit,),
        )
    return list(cursor.fetchall())


def _cald_distribution(cursor) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT preferred_language, cultural_background, count(*) AS patient_count
        FROM c3a_synthea_cald_profiles
        GROUP BY preferred_language, cultural_background
        ORDER BY preferred_language, cultural_background
        """
    )
    return list(cursor.fetchall())


def _rows_for_patients(cursor, table_kind: str, patient_ids: list[str], limit: int) -> list[dict[str, Any]]:
    if not patient_ids:
        return []
    sql = {
        "conditions": """
            SELECT x.*, p.first_name, p.last_name
            FROM c3a_synthea_conditions x
            JOIN c3a_synthea_patients p ON p.id = x.patient_id
            WHERE x.patient_id = ANY(%s::uuid[])
            ORDER BY COALESCE(x.stop_date, x.start_date) DESC NULLS LAST, x.description
            LIMIT %s
        """,
        "medications": """
            SELECT x.*, p.first_name, p.last_name
            FROM c3a_synthea_medications x
            JOIN c3a_synthea_patients p ON p.id = x.patient_id
            WHERE x.patient_id = ANY(%s::uuid[])
            ORDER BY COALESCE(x.stop_at, x.start_at) DESC NULLS LAST, x.description
            LIMIT %s
        """,
        "allergies": """
            SELECT x.*, p.first_name, p.last_name
            FROM c3a_synthea_allergies x
            JOIN c3a_synthea_patients p ON p.id = x.patient_id
            WHERE x.patient_id = ANY(%s::uuid[])
            ORDER BY COALESCE(x.stop_date, x.start_date) DESC NULLS LAST, x.description
            LIMIT %s
        """,
        "encounters": """
            SELECT x.*, p.first_name, p.last_name
            FROM c3a_synthea_encounters x
            JOIN c3a_synthea_patients p ON p.id = x.patient_id
            WHERE x.patient_id = ANY(%s::uuid[])
            ORDER BY x.start_at DESC NULLS LAST, x.description
            LIMIT %s
        """,
    }[table_kind]
    cursor.execute(sql, (patient_ids, limit))
    return list(cursor.fetchall())


def _observations(cursor, patient_ids: list[str], limit: int) -> list[dict[str, Any]]:
    if not patient_ids:
        return []
    cursor.execute(
        """
        SELECT x.*, p.first_name, p.last_name
        FROM c3a_synthea_observations x
        JOIN c3a_synthea_patients p ON p.id = x.patient_id
        WHERE x.patient_id = ANY(%s::uuid[])
        ORDER BY
            CASE WHEN x.description = ANY(%s::text[]) THEN 0 ELSE 1 END,
            x.observed_at DESC NULLS LAST,
            x.description
        LIMIT %s
        """,
        (patient_ids, list(OBSERVATION_PRIORITY), limit),
    )
    return list(cursor.fetchall())


_PATIENT_SELECT = """
    SELECT
        p.id, p.first_name, p.middle_name, p.last_name, p.age, p.gender,
        p.race, p.ethnicity, p.city, p.state, p.healthcare_expenses,
        p.healthcare_coverage, p.income
    FROM c3a_synthea_patients p
"""


def _add_section(sections: list[str], heading: str, body: str) -> None:
    if body:
        sections.append(f"### {heading}\n{body}")


def _build_context(sections: list[str]) -> str:
    return (
        "## Retrieved PostgreSQL Synthetic Patient Context\n"
        "Use this database context when answering questions about the synthetic elderly patient dataset. "
        "Treat these rows as synthetic project data, not real patient records. "
        "Do not invent patient details that are not shown below.\n\n"
        + "\n\n".join(sections)
    )


def _format_patients(rows: list[dict[str, Any]]) -> str:
    lines = []
    for index, row in enumerate(rows, start=1):
        name = _patient_name(row)
        lines.append(
            f"[Patient {index}] ID: {row['id']}; Name: {name}; Age: {row['age']}; "
            f"Gender: {_value(row.get('gender'))}; Race/ethnicity: {_value(row.get('race'))}/{_value(row.get('ethnicity'))}; "
            f"Location: {_value(row.get('city'))}, {_value(row.get('state'))}; "
            f"Healthcare expenses/coverage: {_value(row.get('healthcare_expenses'))}/{_value(row.get('healthcare_coverage'))}; "
            f"Income: {_value(row.get('income'))}."
        )
    return "\n".join(lines)


def _format_cald_profiles(rows: list[dict[str, Any]]) -> str:
    lines = []
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"[CALD Profile {index}] Patient: {_patient_name(row)} ({row['patient_id']}); "
            f"Language: {_value(row.get('preferred_language'))}; Interpreter required: {_value(row.get('interpreter_required'))}; "
            f"Religion: {_value(row.get('religion'))}; Cultural background: {_value(row.get('cultural_background'))}; "
            f"Health literacy: {_value(row.get('health_literacy'))}; Care setting: {_value(row.get('care_setting'))}; "
            f"Dietary notes: {_value(row.get('dietary_notes'))}; Communication notes: {_value(row.get('communication_notes'))}; "
            f"Mobility: {_value(row.get('mobility_support'))}; Cognitive status: {_value(row.get('cognitive_status'))}; "
            f"Emergency contact relationship: {_value(row.get('emergency_contact_relationship'))}; "
            f"Care risk flags: {_jsonish(row.get('care_risk_flags'))}."
        )
    return "\n".join(lines)


def _format_cald_distribution(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[CALD Distribution {index}] Language: {row.get('preferred_language')}; "
        f"Cultural background: {row.get('cultural_background')}; Patients: {row.get('patient_count')}."
        for index, row in enumerate(rows, start=1)
    )


def _format_conditions(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[Condition {index}] Patient: {_patient_name(row)}; Start: {_value(row.get('start_date'))}; "
        f"Stop: {_value(row.get('stop_date'))}; Code: {_value(row.get('code'))}; Description: {row.get('description')}."
        for index, row in enumerate(rows, start=1)
    )


def _format_medications(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[Medication {index}] Patient: {_patient_name(row)}; Start: {_value(row.get('start_at'))}; "
        f"Stop: {_value(row.get('stop_at'))}; Medication: {row.get('description')}; "
        f"Reason: {_value(row.get('reason_description'))}; Dispenses: {_value(row.get('dispenses'))}."
        for index, row in enumerate(rows, start=1)
    )


def _format_allergies(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[Allergy {index}] Patient: {_patient_name(row)}; Start: {_value(row.get('start_date'))}; "
        f"Description: {row.get('description')}; Category: {_value(row.get('category'))}; "
        f"Type: {_value(row.get('allergy_type'))}; Severity: {_value(row.get('severity1') or row.get('severity2'))}."
        for index, row in enumerate(rows, start=1)
    )


def _format_encounters(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[Encounter {index}] Patient: {_patient_name(row)}; Start: {_value(row.get('start_at'))}; "
        f"Stop: {_value(row.get('stop_at'))}; Class: {_value(row.get('encounter_class'))}; "
        f"Description: {_value(row.get('description'))}; Reason: {_value(row.get('reason_description'))}."
        for index, row in enumerate(rows, start=1)
    )


def _format_observations(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[Observation {index}] Patient: {_patient_name(row)}; Date: {_value(row.get('observed_at'))}; "
        f"Category: {_value(row.get('category'))}; Description: {row.get('description')}; "
        f"Value: {_value(row.get('value'))} {_value(row.get('units'))}; Type: {_value(row.get('value_type'))}."
        for index, row in enumerate(rows, start=1)
    )


def _patient_name(row: dict[str, Any]) -> str:
    return " ".join(str(part) for part in [row.get("first_name"), row.get("last_name")] if part) or "Unknown"


def _value(value: Any) -> str:
    if value is None or value == "":
        return "not recorded"
    return str(value)


def _jsonish(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None:
        return "not recorded"
    return str(value)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _safe_error_message(exc: Exception, database_url: str) -> str:
    message = str(exc)
    if database_url and database_url in message:
        message = message.replace(database_url, "[DATABASE_URL]")
    parsed = urlsplit(database_url)
    if parsed.password:
        message = message.replace(parsed.password, "[PASSWORD]")
    if parsed.query:
        message = message.replace(parsed.query, "[QUERY]")
    return message[:500]
