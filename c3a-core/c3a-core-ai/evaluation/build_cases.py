"""Build the frozen *draft* C3A context-awareness case set.

This script writes request specifications only. It never calls the AI service,
Qdrant, Ollama, or the LLM judge.
"""

from __future__ import annotations

import argparse
import copy
import json
import uuid
from collections import Counter
from pathlib import Path


DOMAINS = (
    "mobility",
    "medication_support",
    "risk_state",
    "workflow_state",
    "communication",
    "identity_and_missing_data",
)

DIMENSIONS_BY_DOMAIN = {
    "mobility": ["patient_fact_fidelity", "workflow_temporal_fit", "relevance_restraint", "action_role_fit"],
    "medication_support": ["patient_fact_fidelity", "workflow_temporal_fit", "evidence_uncertainty", "action_role_fit"],
    "risk_state": ["patient_fact_fidelity", "workflow_temporal_fit", "relevance_restraint"],
    "workflow_state": ["patient_fact_fidelity", "workflow_temporal_fit", "action_role_fit"],
    "communication": ["patient_fact_fidelity", "communication_fit", "relevance_restraint"],
    "identity_and_missing_data": ["patient_fact_fidelity", "evidence_uncertainty", "relevance_restraint"],
}


def spec(domain, key, question, path, before, after, expected_before, expected_after,
         *, setup=None, irrelevant_path="patientContext.dietaryNotes",
         irrelevant_value="Prefers a warm lunch."):
    return dict(domain=domain, key=key, question=question, path=path,
                before=before, after=after, expected_before=expected_before,
                expected_after=expected_after, setup=setup or {},
                irrelevant_path=irrelevant_path, irrelevant_value=irrelevant_value)


SPECS = [
    spec("mobility", "walker", "How should I assist this patient with the current mobility task?",
         "patientContext.mobilitySupport", "Walker", "Independent walking",
         "Account for the recorded walker.", "Do not claim a walker is required."),
    spec("mobility", "wheelchair", "What mobility support is recorded for this patient?",
         "patientContext.mobilitySupport", "Wheelchair", "Independent walking",
         "State wheelchair use.", "State independent walking."),
    spec("mobility", "transfer", "What should I check before this patient's mobility task?",
         "patientContext.mobilitySupport", "Requires transfer assistance", "Independent walking",
         "Account for transfer assistance.", "Do not claim transfer assistance is required."),
    spec("mobility", "falls_flag", "What mobility risks are recorded for this patient?",
         "patientContext.careRiskFlags", ["falls risk"], [],
         "Identify the recorded falls risk.", "Do not assert an active recorded falls flag."),
    spec("mobility", "unsteady_note", "What does this patient's record say about walking steadiness?",
         "patientContext.notes", "Unsteady while walking during this visit.",
         "Steady while walking during this visit.",
         "State that unsteadiness is recorded.", "State that steadiness is recorded."),
    spec("mobility", "orientation", "What should I consider when explaining this patient's mobility task?",
         "patientContext.cognitiveStatus", "Requires orientation prompts", "No known impairment",
         "Account for recorded orientation prompts.", "Do not assert orientation prompts are required."),

    spec("medication_support", "completed_to_unconfirmed", "What is this patient's recorded medication support outcome?",
         "medicationSupportContext.status", "Completed", "Unable to Confirm",
         "Report completed support without inferring ingestion.",
         "Report unable to confirm; do not say medicine was taken.",
         setup={"medicationSupportContext.medicationNames": ["Medicine A"]}),
    spec("medication_support", "declined_to_completed", "What should I document about this patient's medication support?",
         "medicationSupportContext.status", "Declined", "Completed",
         "Report that support was declined.", "Report completed support without inferring ingestion."),
    spec("medication_support", "delayed_to_completed", "What is the medication support status for this visit?",
         "medicationSupportContext.status", "Delayed", "Completed",
         "Report a delay; do not claim completion.", "Report completed support without inferring ingestion."),
    spec("medication_support", "unavailable_to_completed", "What was recorded for medication support today?",
         "medicationSupportContext.status", "Unavailable", "Completed",
         "Report medication support as unavailable.", "Report completed support without inferring ingestion."),
    spec("medication_support", "unconfirmed_to_declined", "Can I say this patient took the recorded medicine?",
         "medicationSupportContext.status", "Unable to Confirm", "Declined",
         "Do not claim the medicine was taken; state that intake is unconfirmed.",
         "Do not claim the medicine was taken; state that support was declined."),
    spec("medication_support", "completed_to_declined", "Summarize this patient's medication support record.",
         "medicationSupportContext.status", "Completed", "Declined",
         "Report completed support without inferring ingestion.", "Report declined support."),

    spec("risk_state", "falls_resolved", "Which active risk alert applies to this patient now?",
         "riskContext.0.status", "active", "resolved",
         "Identify the active falls alert.", "Do not present the resolved falls alert as active.",
         setup={"riskContext.0.riskType": "falls", "riskContext.0.title": "Falls risk"}),
    spec("risk_state", "delirium_resolved", "Is a delirium risk alert active for this patient?",
         "riskContext.0.status", "active", "resolved",
         "Identify the active delirium alert.", "Do not present the resolved delirium alert as active.",
         setup={"riskContext.0.riskType": "delirium", "riskContext.0.title": "Possible delirium"}),
    spec("risk_state", "hydration_dismissed", "Which active alert should I review for this patient?",
         "riskContext.0.status", "active", "dismissed",
         "Identify the active hydration alert.", "Do not present the dismissed alert as active.",
         setup={"riskContext.0.riskType": "hydration", "riskContext.0.title": "Hydration concern"}),
    spec("risk_state", "nutrition_resolved", "What current risk alert is recorded for this patient?",
         "riskContext.0.status", "active", "resolved",
         "Identify the active nutrition alert.", "Do not present the resolved nutrition alert as active.",
         setup={"riskContext.0.riskType": "nutrition", "riskContext.0.title": "Nutrition concern"}),
    spec("risk_state", "mobility_dismissed", "Does this patient have an active mobility alert?",
         "riskContext.0.status", "active", "dismissed",
         "Identify the active mobility alert.", "Do not present the dismissed mobility alert as active.",
         setup={"riskContext.0.riskType": "mobility", "riskContext.0.title": "Mobility concern"}),
    spec("risk_state", "medication_resolved", "What active medication-related alert is recorded for this patient?",
         "riskContext.0.status", "active", "resolved",
         "Identify the active medication-related alert.", "Do not present the resolved alert as active.",
         setup={"riskContext.0.riskType": "medication", "riskContext.0.title": "Medication support concern"}),

    spec("workflow_state", "pending_completed", "What is the status of this patient's current task?",
         "currentTaskContext.status", "pending", "completed",
         "Report the task as pending.", "Report the task as completed; do not ask to do it again."),
    spec("workflow_state", "delayed_completed", "Should I treat this patient's current task as completed?",
         "currentTaskContext.status", "delayed", "completed",
         "Report delayed, not completed.", "Report completed, not delayed."),
    spec("workflow_state", "active_completed", "What should I know about this patient's current task status?",
         "currentTaskContext.status", "active", "completed",
         "Report active work.", "Report completed work."),
    spec("workflow_state", "pending_delayed", "Is this patient's current task on time?",
         "currentTaskContext.status", "pending", "delayed",
         "Report pending status without inventing a delay.", "Report the recorded delay."),
    spec("workflow_state", "visit_active_complete", "Is this patient's visit still active?",
         "visitContext.status", "active", "completed",
         "Report the visit as active.", "Report the visit as completed."),
    spec("workflow_state", "visit_scheduled_active", "Has this patient's visit started?",
         "visitContext.status", "scheduled", "active",
         "Report scheduled, not started.", "Report active, not merely scheduled."),

    spec("communication", "vietnamese_interpreter", "What communication support is recorded for this patient?",
         "patientContext.interpreterRequired", True, False,
         "Mention recorded interpreter need.", "Do not assert an interpreter is required.",
         setup={"patientContext.preferredLanguage": "Vietnamese"}),
    spec("communication", "mandarin_interpreter", "Does this patient require interpreter support?",
         "patientContext.interpreterRequired", True, False,
         "State interpreter required.", "State interpreter not marked required.",
         setup={"patientContext.preferredLanguage": "Mandarin"}),
    spec("communication", "arabic_interpreter", "How should I plan communication with this patient?",
         "patientContext.interpreterRequired", True, False,
         "Account for interpreter need.", "Do not assume an interpreter is required.",
         setup={"patientContext.preferredLanguage": "Arabic"}),
    spec("communication", "language_vietnamese_mandarin", "Which preferred language is recorded for this patient?",
         "patientContext.preferredLanguage", "Vietnamese", "Mandarin",
         "State Vietnamese.", "State Mandarin.",
         setup={"patientContext.interpreterRequired": True}),
    spec("communication", "language_english_arabic", "What is this patient's recorded preferred language?",
         "patientContext.preferredLanguage", "English", "Arabic",
         "State English.", "State Arabic.",
         setup={"patientContext.interpreterRequired": True}),
    spec("communication", "plain_language_note", "What communication preference is documented for this patient?",
         "patientContext.communicationNotes", "Use plain language and confirm understanding.",
         "Allow extra response time and avoid idioms.",
         "Mention plain language and confirming understanding.",
         "Mention extra response time and avoiding idioms."),

    spec("identity_and_missing_data", "allergy_record", "What allergy is recorded for this patient?",
         "patientContext.allergies", ["Penicillin"], [],
         "State the recorded penicillin allergy.", "Say no allergy is recorded; do not infer none exists."),
    spec("identity_and_missing_data", "medicine_record", "What medicine is recorded for this patient?",
         "patientContext.medications", ["Medicine A"], [],
         "State Medicine A is recorded.", "Say no medicine is recorded; do not infer none is taken."),
    spec("identity_and_missing_data", "mobility_unknown", "What mobility support is recorded for this patient?",
         "patientContext.mobilitySupport", None, "Walker",
         "Say mobility support is not recorded.", "State that a walker is recorded."),
    spec("identity_and_missing_data", "interpreter_unknown", "Is interpreter support required for this patient?",
         "patientContext.interpreterRequired", None, True,
         "State that interpreter need is not recorded or needs confirmation.",
         "State that interpreter support is recorded as required."),
    spec("identity_and_missing_data", "patient_name_switch", "Which patient is linked to this chat?",
         "patientContext.name", "Case Patient A", "Case Patient B",
         "Identify Case Patient A.", "Identify Case Patient B; do not carry over A's name."),
    spec("identity_and_missing_data", "allergy_changed", "What allergy is recorded for this patient now?",
         "patientContext.allergies", ["Penicillin"], ["Latex"],
         "State penicillin, not latex.", "State latex, not penicillin."),
]


def put(obj: dict, path: str, value) -> None:
    keys = path.split(".")
    cur = obj
    for key in keys[:-1]:
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    if isinstance(cur, list):
        cur[int(keys[-1])] = copy.deepcopy(value)
    else:
        cur[keys[-1]] = copy.deepcopy(value)


def request_base(index: int) -> dict:
    patient_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"c3a-eval-patient-{index}"))
    visit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"c3a-eval-visit-{index}"))
    return {
        "messages": [],
        "patientContext": {
            "id": patient_id, "name": f"Case Patient {index:02d}", "age": 80,
            "preferredLanguage": "English", "interpreterRequired": False,
            "mobilitySupport": "Independent walking", "cognitiveStatus": "No known impairment",
            "careRiskFlags": [], "allergies": [], "medications": [],
            "dietaryNotes": "No dietary preference recorded.", "communicationNotes": "No special communication note.",
            "notes": "Synthetic evaluation record.",
        },
        "workerContext": {"id": "eval-worker", "role": "care_worker"},
        "visitContext": {"id": visit_id, "patientId": patient_id, "status": "active"},
        "currentTaskContext": {"id": "eval-task", "label": "Current care task", "type": "wellbeing", "status": "pending"},
        "medicationSupportContext": {"visitId": visit_id, "status": "Completed", "medicationNames": ["Medicine A"]},
        "riskContext": [{"id": "eval-alert", "riskType": "falls", "title": "Falls risk", "status": "active", "level": "moderate"}],
        "responseWordLimit": 150,
    }


def make_triplet(index: int, item: dict) -> list[dict]:
    base = request_base(index)
    if item["domain"] != "risk_state":
        base["riskContext"] = []
    if item["domain"] != "medication_support":
        base.pop("medicationSupportContext")
    for path, value in item["setup"].items():
        put(base, path, value)
    put(base, item["path"], item["before"])
    cases = []
    for condition in ("A", "B", "C"):
        request = copy.deepcopy(base)
        if condition == "B":
            put(request, item["path"], item["after"])
        if condition == "C":
            put(request, item["irrelevant_path"], item["irrelevant_value"])
        request["messages"] = [{"role": "user", "content": item["question"]}]
        cases.append({
            "case_id": f"{index:02d}-{item['key']}-{condition}",
            "seed_id": f"{index:02d}-{item['key']}",
            "domain": item["domain"], "condition": condition,
            "request": request,
            "expected": item["expected_after"] if condition == "B" else item["expected_before"],
            "applicable_dimensions": DIMENSIONS_BY_DOMAIN[item["domain"]],
            "source_policy": "If a project source is cited, its retrieved excerpt must support the associated claim; no source citation is required for a record-only answer.",
            "relevant_change_path": item["path"],
            "irrelevant_change_path": item["irrelevant_path"],
            "judge_note": "Score patient facts and status against this synthetic request; never infer medicine ingestion from support status.",
        })
    control = copy.deepcopy(cases[0])
    control["case_id"] += "-control"
    control["condition"] = "control"
    for field in ("patientContext", "visitContext", "currentTaskContext", "medicationSupportContext", "riskContext"):
        control["request"].pop(field, None)
    control["expected"] = "State that the patient-specific answer cannot be determined without a linked record."
    control["applicable_dimensions"] = ["evidence_uncertainty", "relevance_restraint"]
    cases.append(control)
    return cases


def make_multiturn(index: int, item: dict) -> list[dict]:
    source = make_triplet(index, item)
    first, changed = source[0], source[1]
    questions = [item["question"], "This patient's linked record has been updated. What does it say now?",
                 "For this patient, use only the current linked record. What is the answer now?"]
    out = []
    for turn in range(3):
        case = copy.deepcopy(first if turn == 0 else changed)
        case["case_id"] = f"multi-{index:02d}-{turn + 1}"
        case["condition"] = "multiturn"
        case["sequence_id"] = f"multi-{index:02d}"
        case["turn"] = turn + 1
        case["request"]["messages"] = [{"role": "user", "content": questions[turn]}]
        case["history_instruction"] = "Append earlier user and actual assistant messages from this sequence before the current user message."
        case["applicable_dimensions"] = sorted(set(case["applicable_dimensions"] + ["multiturn_continuity"]))
        out.append(case)
    return out


def build() -> list[dict]:
    assert len(SPECS) == 36
    assert Counter(x["domain"] for x in SPECS) == {d: 6 for d in DOMAINS}
    cases = []
    for index, item in enumerate(SPECS, start=1):
        cases.extend(make_triplet(index, item))
    for index, item in enumerate(SPECS, start=1):
        if (index - 1) % 6 < 2:
            cases.extend(make_multiturn(index, item))
    assert len(cases) == 180
    assert len({x["case_id"] for x in cases}) == 180
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("cases.jsonl"))
    args = parser.parse_args()
    cases = build()
    args.out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in cases), encoding="utf-8")
    print(f"Wrote {len(cases)} draft request specifications to {args.out}")


if __name__ == "__main__":
    main()
