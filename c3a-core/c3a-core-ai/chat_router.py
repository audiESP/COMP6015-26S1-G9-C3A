"""Deterministic retrieval routing for chat questions.

The router decides whether a user question should use synthetic PostgreSQL
patient data, Qdrant RAG evidence, both, neither, or an ambiguity-resolving
double retrieval pass.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import UUID


RetrievalMode = Literal[
    "database_only",
    "rag_only",
    "hybrid",
    "direct_ai",
    "uncertain",
]


@dataclass(frozen=True)
class RouteDecision:
    mode: RetrievalMode
    uses_db: bool
    uses_rag: bool
    confidence: float
    reason: str
    matched_signals: list[str]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

PATIENT_ANCHOR_PHRASES = {
    "this patient",
    "that patient",
    "the patient",
    "this resident",
    "that resident",
    "the resident",
    "resident record",
    "patient record",
    "her medications",
    "his medications",
    "their medications",
    "her allergies",
    "his allergies",
    "their allergies",
    "her vitals",
    "his vitals",
    "their vitals",
    "latest vitals",
    "observations for this patient",
}

DB_FACT_TERMS = {
    "allergy",
    "allergies",
    "cald",
    "condition",
    "conditions",
    "database",
    "demographic",
    "demographics",
    "diagnosis",
    "diagnoses",
    "encounter",
    "encounters",
    "gender",
    "income",
    "lab",
    "labs",
    "language",
    "medication",
    "medications",
    "medicine",
    "observation",
    "observations",
    "patient",
    "patients",
    "profile",
    "profiles",
    "record",
    "records",
    "resident",
    "residents",
    "synthea",
    "vital",
    "vitals",
}

DB_FACT_PHRASES = {
    "blood pressure",
    "cald profile",
    "care risk flags",
    "health literacy",
    "language distribution",
    "medical history",
    "past medical history",
    "previous progress notes",
    "progress notes",
    "progress note",
    "home care visit records",
    "home care visit record",
    "previous home care visit records",
    "patient data",
    "patient details",
    "patient facts",
    "synthetic dataset",
}

GUIDELINE_TERMS = {
    "action",
    "actions",
    "advice",
    "caregiver",
    "escalate",
    "escalation",
    "evidence",
    "guidance",
    "guideline",
    "guidelines",
    "manage",
    "management",
    "monitor",
    "monitoring",
    "pathway",
    "pathways",
    "practice",
    "recommend",
    "recommended",
    "recommendation",
    "recommendations",
    "restorative",
    "safety",
    "steps",
    "support",
    "warning",
}

GUIDELINE_PHRASES = {
    "aged care",
    "at home",
    "care worker",
    "end of life",
    "end-of-life",
    "ongoing support",
    "red flag",
    "red flags",
    "restorative care",
    "safe medication management",
    "warning signs",
    "what should i do",
    "what should we do",
}

WORKFLOW_ACTION_PHRASES = {
    "how should",
    "how to",
    "need to do",
    "should the care worker",
    "what should",
    "what to do",
}

AMBIGUOUS_OVERLAP_TERMS = {
    "cald",
    "care",
    "fall",
    "falls",
    "medication",
    "medications",
    "mobility",
    "observation",
    "observations",
    "risk",
    "risks",
}

AMBIGUOUS_OVERLAP_PHRASES = {
    "care plan",
    "fall risk",
    "medication management",
}

GENERIC_MEDICAL_TERMS = {
    "adult",
    "adults",
    "allergy",
    "allergies",
    "care",
    "clinical",
    "condition",
    "conditions",
    "fall",
    "falls",
    "health",
    "medical",
    "medication",
    "medications",
    "mobility",
    "patient",
    "patients",
    "resident",
    "residents",
    "risk",
    "risks",
}

DATASET_INTENT_TERMS = {
    "count",
    "counts",
    "data",
    "database",
    "dataset",
    "distribution",
    "list",
    "records",
    "show",
    "synthea",
}


def decide_route(query: str, patient_context: Any = None, attachments: Any = None) -> RouteDecision:
    """Return the initial retrieval route for a chat question."""

    if not query or not query.strip():
        return _decision(
            "direct_ai",
            0.95,
            "Empty query; no retrieval needed.",
            ["empty_query"],
        )

    lowered = query.lower()
    words = set(re.findall(r"[a-z][a-z-]*", lowered))
    signals: list[str] = []

    patient_anchor = _has_patient_anchor(lowered, query, patient_context)
    if patient_anchor:
        signals.extend(patient_anchor)

    db_signals = _db_signals(words, lowered)
    guideline_signals = _guideline_signals(words, lowered)
    workflow_signals = _workflow_signals(words, lowered)
    overlap_signals = _overlap_signals(words, lowered)
    dataset_signals = _dataset_signals(words, lowered)
    attachment_signals = _attachment_signals(attachments)
    signals.extend(db_signals)
    signals.extend(guideline_signals)
    signals.extend(workflow_signals)
    signals.extend(overlap_signals)
    signals.extend(dataset_signals)
    signals.extend(attachment_signals)
    signals = _dedupe(signals)

    has_patient_anchor = bool(patient_anchor)
    has_db_fact = bool(db_signals or dataset_signals)
    has_guideline = bool(guideline_signals)
    has_workflow = bool(workflow_signals)
    has_overlap = bool(overlap_signals)
    has_medical = bool(words & GENERIC_MEDICAL_TERMS) or has_db_fact or has_guideline or has_overlap

    if not has_medical and not attachment_signals:
        return _decision(
            "direct_ai",
            0.9,
            "No patient, database, guideline, or clinical-care signal was found.",
            signals or ["no_retrieval_signal"],
        )

    if has_patient_anchor and has_db_fact and (has_guideline or has_workflow):
        return _decision(
            "hybrid",
            0.9,
            "Patient-specific facts and care guidance are both requested.",
            signals,
        )

    if has_patient_anchor and has_overlap and (has_guideline or has_workflow):
        return _decision(
            "hybrid",
            0.82,
            "Patient anchor plus overlapping clinical-care terms need both patient facts and guidance.",
            signals,
        )

    if has_patient_anchor and has_db_fact:
        return _decision(
            "database_only",
            0.88,
            "Patient-specific record facts are requested.",
            signals,
        )

    if has_patient_anchor and has_overlap:
        return _decision(
            "database_only",
            0.74,
            "Patient anchor with overlapping terms is most likely asking for patient record facts.",
            signals,
        )

    if has_guideline and not has_db_fact:
        return _decision(
            "rag_only",
            0.86,
            "Guideline, pathway, or care-practice evidence is requested.",
            signals,
        )

    if has_guideline and has_db_fact and not has_patient_anchor:
        if dataset_signals or _has_plural_resident_scope(words, lowered):
            return _decision(
                "uncertain",
                0.52,
                "Both database and guideline signals are present without a patient anchor.",
                signals,
            )
        return _decision(
            "rag_only",
            0.72,
            "Guidance appears primary and no patient anchor was provided.",
            signals,
        )

    if has_overlap and not has_patient_anchor:
        if has_workflow and not dataset_signals and not _has_plural_resident_scope(words, lowered):
            return _decision(
                "rag_only",
                0.72,
                "Overlapping care term appears to ask for general care guidance.",
                signals,
            )
        return _decision(
            "uncertain",
            0.5,
            "Overlapping database/RAG terms are present without enough intent to choose one source.",
            signals,
        )

    if has_db_fact:
        return _decision(
            "database_only",
            0.72,
            "Database fact terms are present and no guideline intent was found.",
            signals,
        )

    if attachment_signals:
        return _decision(
            "direct_ai",
            0.76,
            "Attachment-only clinical question should be handled directly by the model.",
            signals,
        )

    return _decision(
        "direct_ai",
        0.55,
        "No strong retrieval source was identified.",
        signals or ["weak_retrieval_signal"],
    )


def with_effective_mode(
    decision: RouteDecision,
    effective_mode: RetrievalMode,
    reason: str | None = None,
) -> RouteDecision:
    """Create a follow-up decision after retrieval-quality resolution."""

    return _decision(
        effective_mode,
        decision.confidence,
        reason or decision.reason,
        decision.matched_signals,
    )


def _decision(
    mode: RetrievalMode,
    confidence: float,
    reason: str,
    matched_signals: list[str],
) -> RouteDecision:
    return RouteDecision(
        mode=mode,
        uses_db=mode in {"database_only", "hybrid", "uncertain"},
        uses_rag=mode in {"rag_only", "hybrid", "uncertain"},
        confidence=round(max(0.0, min(1.0, confidence)), 2),
        reason=reason,
        matched_signals=_dedupe(matched_signals),
    )


def _has_patient_anchor(lowered: str, raw_query: str, patient_context: Any) -> list[str]:
    signals: list[str] = []
    has_anchor_phrase = any(phrase in lowered for phrase in PATIENT_ANCHOR_PHRASES)
    patient_id = getattr(patient_context, "id", None)
    if _normalise_uuid(patient_id) and has_anchor_phrase:
        signals.append("patient_context_id")
    patient_name = getattr(patient_context, "name", None)
    if isinstance(patient_name, str) and patient_name.strip():
        name_parts = [part.lower() for part in re.findall(r"[A-Za-z]{2,}", patient_name)]
        if any(part in lowered for part in name_parts):
            signals.append("patient_context_name")
    if UUID_PATTERN.search(raw_query):
        signals.append("patient_uuid_in_query")
    if has_anchor_phrase:
        signals.append("patient_anchor_phrase")
    return _dedupe(signals)


def _db_signals(words: set[str], lowered: str) -> list[str]:
    signals = []
    if words & DB_FACT_TERMS:
        signals.append("patient_record_term")
    if any(phrase in lowered for phrase in DB_FACT_PHRASES):
        signals.append("database_fact_phrase")
    return signals


def _guideline_signals(words: set[str], lowered: str) -> list[str]:
    signals = []
    if words & GUIDELINE_TERMS:
        signals.append("guideline_term")
    if any(phrase in lowered for phrase in GUIDELINE_PHRASES):
        signals.append("guideline_phrase")
    return signals


def _workflow_signals(words: set[str], lowered: str) -> list[str]:
    signals = []
    if any(phrase in lowered for phrase in WORKFLOW_ACTION_PHRASES):
        signals.append("workflow_action_phrase")
    if {"should", "monitor", "manage", "steps", "action", "actions"} & words:
        signals.append("workflow_action_term")
    return signals


def _overlap_signals(words: set[str], lowered: str) -> list[str]:
    signals = []
    if words & AMBIGUOUS_OVERLAP_TERMS:
        signals.append("ambiguous_overlap_term")
    if any(phrase in lowered for phrase in AMBIGUOUS_OVERLAP_PHRASES):
        signals.append("ambiguous_overlap_phrase")
    return signals


def _dataset_signals(words: set[str], lowered: str) -> list[str]:
    signals = []
    if words & DATASET_INTENT_TERMS:
        signals.append("dataset_query_term")
    if "language distribution" in lowered:
        signals.append("dataset_distribution_phrase")
    return signals


def _attachment_signals(attachments: Any) -> list[str]:
    if not attachments:
        return []
    for attachment in attachments:
        mime_type = getattr(attachment, "mimeType", "")
        if isinstance(mime_type, str) and mime_type.startswith("image/"):
            return ["image_attachment"]
    return ["attachment"]


def _has_plural_resident_scope(words: set[str], lowered: str) -> bool:
    return bool({"residents", "patients"} & words) or "older adults" in lowered


def _normalise_uuid(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
