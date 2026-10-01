"""Replace the two post-fix reports with a labelled 52-case targeted rerun update."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
OUT = ROOT / ".codex-output"
DATE = "2026-10-01"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def all_two(scores: dict) -> bool:
    return all(value == 2 for value in scores.values() if value is not None)


def summary(verdicts: dict[str, dict]) -> dict:
    return {
        "all_two": sum(all_two(row["scores"]) for row in verdicts.values()),
        "any_zero": sum(any(value == 0 for value in row["scores"].values()) for row in verdicts.values()),
        "critical": sum(bool(row["critical_errors"]) for row in verdicts.values()),
    }


def main() -> None:
    cases = {r["case_id"]: r for r in rows(HERE / "cases.jsonl")}
    selected = set(json.loads((RESULTS / f"failed_case_ids_{DATE}.json").read_text()))
    old_responses = {r["case_id"]: r for r in rows(RESULTS / f"cloud_full_after_refresh_{DATE}.jsonl")}
    new_responses = {r["case_id"]: r for r in rows(RESULTS / f"failed_rerun_{DATE}.jsonl")}
    fixture = json.loads((RESULTS / f"failed_rerun_manifest_{DATE}.json").read_text())
    if len(cases) != 180 or len(old_responses) != 180 or len(selected) != 52 or set(new_responses) != selected:
        raise ValueError("Expected full baseline and exactly the 52 selected cases")
    if fixture["status"] != "cleaned" or fixture["cleanup"]["remaining_patient_rows"] != 0 or not fixture["cleanup"]["case_table_removed"]:
        raise ValueError("Cloud fixture cleanup is incomplete")
    if any(r.get("error") or r.get("http_status") != 200 for r in new_responses.values()):
        raise ValueError("Rerun has a failed response")

    review_map = json.loads((RESULTS / f"inchat_full_after_refresh_map_{DATE}.json").read_text())
    old_chat = {review_map[r["review_id"]]: r for r in rows(RESULTS / f"inchat_judge_full_after_refresh_{DATE}.jsonl")}
    new_chat = {r["case_id"]: r for r in rows(RESULTS / f"inchat_judge_failed_rerun_{DATE}.jsonl")}
    old_llama = {r["case_id"]: r["verdict"] for r in rows(RESULTS / f"llama3_judge_full_after_refresh_{DATE}.jsonl")}
    new_llama = {}
    for r in rows(RESULTS / f"llama3_judge_failed_rerun_{DATE}.jsonl"):
        if r.get("error") or not r.get("verdict"):
            raise ValueError(f"Llama rerun failed: {r['case_id']}")
        new_llama[r["case_id"]] = r["verdict"]
    if any(len(group) != expected for group, expected in ((old_chat,180),(old_llama,180),(new_chat,52),(new_llama,52))):
        raise ValueError("Judge coverage is incomplete or has duplicate IDs")
    if set(new_chat) != selected or set(new_llama) != selected:
        raise ValueError("Selected case IDs and judge outputs differ")
    for judge in (old_chat, new_chat, old_llama, new_llama):
        for cid, row in judge.items():
            if set(row["scores"]) != set(cases[cid]["applicable_dimensions"]):
                raise ValueError(f"Dimension mismatch in {cid}")
    for cid, row in new_llama.items():
        if cases[cid].get("condition") == "multiturn" and cases[cid].get("turn") == 1:
            row["scores"]["multiturn_continuity"] = None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    shared = f"""Generated {stamp}. This is a **targeted update**, not a new 180-request run. The previous current-chat review had 52 cases with at least one applicable score below 2. Those exact 52 requests were rerun after the structured-fact fix; the other 128 responses and their scores retain the earlier post-fix run. The combined 180-case view below replaces each selected case with its new response and new verdict. Never use it as a paired 180-case before/after estimate.

The rerun created 22 isolated fictional PostgreSQL patient rows and 65 stored case specifications (52 selected cases plus baselines needed to create the fixtures). All 52 requests returned HTTP 200. The run manifest confirms all 22 patient rows and the temporary case table were removed; the runner checks fixture UUID ownership before each update. Other patient data and Qdrant were not changed by this run. No clinician adjudication was performed.

The 0–2 scale remains the project's operational rubric, not a validated clinical safety score. Turn-one continuity is N/A.

"""
    for label, old, new, name in (
        ("current-chat model",old_chat,new_chat,f"C3A_180_InChat_After_Refresh_Report_{DATE}.md"),
        ("Llama3",old_llama,new_llama,f"C3A_180_Llama3_After_Refresh_Report_{DATE}.md"),
    ):
        composite = old | new
        base_stats = summary(old)
        selected_before = summary({cid:old[cid] for cid in selected})
        selected_after = summary(new)
        combined = summary(composite)
        case_lines = ["| Case | Previous all-2 | Rerun all-2 | Rerun critical | Rerun answer method |", "|---|---:|---:|---:|---|"]
        for cid in sorted(selected):
            method = new_responses[cid]["response"]["rag"].get("answer_method", "model")
            case_lines.append(f"| `{cid}` | {'yes' if all_two(old[cid]['scores']) else 'no'} | {'yes' if all_two(new[cid]['scores']) else 'no'} | {'yes' if new[cid]['critical_errors'] else 'no'} | {method} |")
        note = ("The answer generator and this judge are both local Llama3. Prior calibration showed false negatives; its high scores cannot serve as the sole pass/fail authority."
                if label == "Llama3" else
                "The conversation model reviewed the new responses case by case with the same record-specific rubric; its exact deployment ID and inference settings are not attested by the saved files.")
        report = f"""# C3A targeted rerun update — {label}

{shared}## Result

| Scope | All applicable dimensions 2 | Any 0 | Critical cases |
|---|---:|---:|---:|
| Original 180 responses | {base_stats['all_two']}/180 | {base_stats['any_zero']}/180 | {base_stats['critical']}/180 |
| Selected 52 before rerun | {selected_before['all_two']}/52 | {selected_before['any_zero']}/52 | {selected_before['critical']}/52 |
| Same 52 after rerun | {selected_after['all_two']}/52 | {selected_after['any_zero']}/52 | {selected_after['critical']}/52 |
| Combined view: 52 new + 128 unchanged | {combined['all_two']}/180 | {combined['any_zero']}/180 | {combined['critical']}/180 |

{note}

The current-chat review found that 27/52 rerun cases now have all applicable scores at 2. The remaining failures concentrate in advice or summary generation with missing context, medication-support status omissions, task timing inferences, and tangential source citations. The narrow structured-record path improves factual questions but does not fix all model-generated replies.

## Selected cases

{chr(10).join(case_lines)}

## Files and provenance

- `c3a-core-ai/evaluation/results/failed_rerun_{DATE}.jsonl`: 52 new requests and responses.
- `c3a-core-ai/evaluation/results/failed_rerun_manifest_{DATE}.json`: fixture ownership and cleanup.
- `c3a-core-ai/evaluation/results/{'inchat_judge' if label == 'current-chat model' else 'llama3_judge'}_failed_rerun_{DATE}.jsonl`: 52 new verdicts.
- The original 180-response and verdict files remain saved. A copy of the previous report is retained beside this file with `Before_Targeted_Rerun` in its name.
"""
        path = OUT / name
        backup = OUT / name.replace("After_Refresh_Report", "Before_Targeted_Rerun_Report")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(report)
    manifest = {
        "date":DATE,"selected_cases":len(selected),"cloud_cleanup":fixture["cleanup"],
        "current_chat_after":summary(old_chat|new_chat),"llama3_after":summary(old_llama|new_llama),
        "sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            RESULTS/f"failed_case_ids_{DATE}.json", RESULTS/f"failed_rerun_{DATE}.jsonl",
            RESULTS/f"failed_rerun_manifest_{DATE}.json", RESULTS/f"inchat_judge_failed_rerun_{DATE}.jsonl",
            RESULTS/f"llama3_judge_failed_rerun_{DATE}.jsonl")},
    }
    (OUT/f"C3A_52_Targeted_Rerun_Manifest_{DATE}.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))


if __name__ == "__main__":
    main()
