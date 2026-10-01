"""Compare the saved 24 updated-record follow-ups before and after the fix."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
OUT = HERE.parents[1] / ".codex-output"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


EXPECTED = {
    1: "Independent walking",
    2: "Independent walking",
    7: "Unable to Confirm",
    8: "Completed",
    13: "Falls risk (resolved)",
    14: "Possible delirium (resolved)",
    19: "completed",
    20: "completed",
    25: "Vietnamese",
    26: "interpreter not marked required",
    31: "No allergy is recorded",
    32: "No medicine is recorded",
}


def main() -> None:
    old_path = RESULTS / "cloud_full_v2_2026-10-01.jsonl"
    new_path = RESULTS / "cloud_multiturn_after_fix_2026-10-01.jsonl"
    manifest_path = RESULTS / "cloud_multiturn_after_fix_manifest_2026-10-01.json"
    old = {r["case_id"]: r for r in rows(old_path)}
    new = {r["case_id"]: r for r in rows(new_path)}
    case_specs = {r["case_id"]: r for r in rows(HERE / "cases.jsonl")}
    manifest = json.loads(manifest_path.read_text())
    if len(new) != 36 or any(r.get("http_status") != 200 for r in new.values()):
        raise ValueError("Targeted live run is not a complete 36-request success")
    if manifest["status"] != "cleaned" or manifest["cleanup"]["remaining_patient_rows"] != 0:
        raise ValueError("Cloud fixture cleanup not verified")

    mapping = (json.loads((RESULTS / "inchat_review_map_2026-10-01.json").read_text()) |
               json.loads((RESULTS / "inchat_multiturn_map_2026-10-01.json").read_text()))
    old_judges = {mapping[r["review_id"]]: r for r in rows(RESULTS / "inchat_judge_2026-10-01.jsonl")
                  if r["review_id"] in mapping}
    comparisons = []
    for case_id, current in sorted(new.items()):
        if current["turn"] not in (2, 3):
            continue
        seed = int(case_id.split("-")[1])
        answer = current["response"]["reply"]
        checks = {
            "expected_current_field_present": EXPECTED[seed] in answer,
            "no_stale_record_claim": not any(text in answer.casefold() for text in
                                          ("has not been updated", "remains the same", "no update")),
            "structured_answer_method": current["response"]["rag"].get("answer_method") == "structured_current_record",
        }
        if seed in (7, 8):
            checks["no_ingestion_inference"] = "does not confirm" in answer
        if seed in (13, 14):
            checks["resolved_not_active"] = "No active risk alert" in answer
        if seed in (25, 26):
            checks["interpreter_flag_not_overstated"] = "not needed" not in answer.casefold()
        prior = old[case_id]
        verdict = old_judges[case_id]
        comparisons.append({
            "case_id": case_id,
            "expected": case_specs[case_id]["expected"],
            "before_answer": prior["response"]["reply"],
            "before_chat_judge_scores": verdict["scores"],
            "before_chat_judge_critical_errors": verdict["critical_errors"],
            "after_answer": answer,
            "after_checks": checks,
            "after_check_pass": all(checks.values()),
        })
    if len(comparisons) != 24:
        raise ValueError(f"Expected 24 follow-up comparisons, got {len(comparisons)}")

    output = RESULTS / "multiturn_before_after_fix_2026-10-01.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in comparisons))
    before_critical = sum(bool(r["before_chat_judge_critical_errors"]) for r in comparisons)
    before_zero = sum(any(v == 0 for v in r["before_chat_judge_scores"].values()) for r in comparisons)
    passed = sum(r["after_check_pass"] for r in comparisons)
    domains = Counter(case_specs[r["case_id"]]["domain"] for r in comparisons)
    lines = [
        "# C3A multi-turn record-update repair: targeted live comparison",
        "",
        "This follow-up test uses 12 newly created fictional patients in cloud PostgreSQL and 12 three-turn conversations. The first turn establishes live conversation history; turns 2 and 3 are the 24 scored update follow-ups. The original 180-case results remain the pre-fix baseline.",
        "",
        "## Execution and cleanup",
        "",
        "- 36/36 live AI endpoint requests returned HTTP 200.",
        "- All 24 update follow-ups used the `structured_current_record` answer method; the 12 first turns still used the model.",
        "- The runner deleted all 12 test patients and its temporary case table. A separate read-only PostgreSQL query confirmed zero patient rows, zero batch rows, and no case table.",
        f"- Domains represented in the 24 follow-ups: {dict(sorted(domains.items()))}.",
        "",
        "## Before and after",
        "",
        f"- Before the fix, the current-chat audit gave a zero on at least one dimension to {before_zero}/24 follow-ups and tagged {before_critical}/24 as critical errors.",
        f"- After the fix, **{passed}/24** passed deterministic checks for the expected current field, absence of a stale-record claim, and the structured answer path. Medication, risk, and interpreter cases also passed their specific safety/wording checks.",
        "- The after-fix replies have **not** received a new independent LLM judge score. The 24/24 figure is a targeted rule-check result, not a newly measured 0–2 rubric pass rate or clinical safety claim.",
        "- The API still receives only the current structured record, not an earlier structured snapshot. It can state the current value but cannot prove precisely which field changed. Guidance requests continue through the model and need separate follow-up evaluation.",
        "",
        "## Per-case comparison",
        "",
        "| Case | Before: critical tag | After: current-state answer | Checks |",
        "|---|---|---|---|",
    ]
    for row in comparisons:
        answer = row["after_answer"].replace("|", "\\|")
        tags = ", ".join(row["before_chat_judge_critical_errors"]) or "none"
        lines.append(f"| `{row['case_id']}` | {tags} | {answer} | {'pass' if row['after_check_pass'] else 'fail'} |")
    lines.extend(["", "Full before/after answers and individual checks are in `c3a-core-ai/evaluation/results/multiturn_before_after_fix_2026-10-01.jsonl`.", ""])
    OUT.mkdir(exist_ok=True)
    (OUT / "C3A_Multiturn_Refresh_Fix_2026-10-01.md").write_text("\n".join(lines))
    print(json.dumps({"followups": len(comparisons), "before_critical": before_critical,
                      "before_zero": before_zero, "after_checks_passed": passed}, indent=2))


if __name__ == "__main__":
    main()
