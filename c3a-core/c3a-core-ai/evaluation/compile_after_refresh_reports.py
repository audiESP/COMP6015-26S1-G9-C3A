"""Compile separate full-coverage reports for the post-fix cloud run."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVAL = Path(__file__).resolve().parent
RESULTS = EVAL / "results"
OUT = ROOT / ".codex-output"
DATE = "2026-10-01"


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(rows: dict[str, dict]) -> dict:
    grades = Counter(str(v) for row in rows.values() for v in row["scores"].values())
    critical = Counter(tag for row in rows.values() for tag in row["critical_errors"])
    return {
        "grades": grades,
        "critical_tags": critical,
        "critical_cases": sum(bool(row["critical_errors"]) for row in rows.values()),
        "zero_cases": sum(any(v == 0 for v in row["scores"].values()) for row in rows.values()),
        "all_two_cases": sum(all(v == 2 for v in row["scores"].values() if v is not None)
                             for row in rows.values()),
    }


def breakdown(rows: dict[str, dict], cases: dict[str, dict], field: str) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for cid, row in rows.items():
        groups[cases[cid][field]].append(row)
    lines = [f"| {field} | Cases | All applicable scores 2 | Any 0 | Critical cases |",
             "|---|---:|---:|---:|---:|"]
    for label, group in sorted(groups.items()):
        full = sum(all(v == 2 for v in row["scores"].values() if v is not None) for row in group)
        zero = sum(any(v == 0 for v in row["scores"].values()) for row in group)
        critical = sum(bool(row["critical_errors"]) for row in group)
        lines.append(f"| {label} | {len(group)} | {full} | {zero} | {critical} |")
    return "\n".join(lines)


def main() -> None:
    case_path = EVAL / "cases.jsonl"
    response_path = RESULTS / f"cloud_full_after_refresh_{DATE}.jsonl"
    fixture_path = RESULTS / f"cloud_full_after_refresh_manifest_{DATE}.json"
    llama_path = RESULTS / f"llama3_judge_full_after_refresh_{DATE}.jsonl"
    chat_path = RESULTS / f"inchat_judge_full_after_refresh_{DATE}.jsonl"
    map_path = RESULTS / f"inchat_full_after_refresh_map_{DATE}.json"
    old_llama_path = RESULTS / f"llama3_judge_cloud_full_{DATE}.jsonl"
    old_chat_path = RESULTS / f"inchat_judge_{DATE}.jsonl"
    cases = {r["case_id"]: r for r in read_rows(case_path)}
    responses = {r["case_id"]: r for r in read_rows(response_path)}
    llama_raw = read_rows(llama_path)
    chat_raw = read_rows(chat_path)
    mapping = json.loads(map_path.read_text())
    if not all(len(obj) == 180 for obj in (cases, responses, llama_raw, chat_raw, mapping)):
        raise ValueError("Every post-fix case, response, and judge file must contain 180 unique rows")
    if any(r.get("error") or r.get("http_status") != 200 for r in responses.values()):
        raise ValueError("Response run contains a failed request")
    fixture = json.loads(fixture_path.read_text())
    if (fixture["status"] != "cleaned" or fixture["cleanup"]["remaining_patient_rows"] != 0
            or not fixture["cleanup"]["case_table_removed"]):
        raise ValueError("Cloud fixture cleanup was not verified")
    if set(cases) != set(responses) or set(cases) != set(mapping.values()):
        raise ValueError("Case IDs differ across files")

    llama = {}
    for row in llama_raw:
        if row.get("error") or not row.get("verdict"):
            raise ValueError(f"Llama3 judge failed for {row['case_id']}")
        cid = row["case_id"]
        if cid in llama:
            raise ValueError(f"Duplicate Llama3 verdict: {cid}")
        verdict = row["verdict"]
        scores = dict(verdict["scores"])
        if set(scores) != set(cases[cid]["applicable_dimensions"]):
            raise ValueError(f"Llama3 dimension mismatch: {cid}")
        if cases[cid]["condition"] == "multiturn" and cases[cid]["turn"] == 1:
            scores["multiturn_continuity"] = None
        llama[cid] = {"scores": scores, "critical_errors": sorted(set(verdict["critical_errors"]))}
    chat = {}
    for row in chat_raw:
        cid = mapping[row["review_id"]]
        if cid in chat or set(row["scores"]) != set(cases[cid]["applicable_dimensions"]):
            raise ValueError(f"Current-chat verdict invalid or duplicated: {cid}")
        if any(v is not None and v < 2 and not row["reasons"].get(key)
               for key, v in row["scores"].items()):
            raise ValueError(f"Current-chat verdict missing a reason: {cid}")
        chat[cid] = {"scores": row["scores"], "critical_errors": sorted(set(row["critical_errors"]))}
    if set(cases) != set(llama) or set(cases) != set(chat):
        raise ValueError("Judge case coverage incomplete")

    old_llama = {row["case_id"]: row for row in read_rows(old_llama_path)}
    old_map = (json.loads((RESULTS / f"inchat_review_map_{DATE}.json").read_text()) |
               json.loads((RESULTS / f"inchat_multiturn_map_{DATE}.json").read_text()) |
               json.loads((RESULTS / f"inchat_critical_map_{DATE}.json").read_text()))
    old_chat = {old_map[row["review_id"]]: row for row in read_rows(old_chat_path)}
    old_multi = {cid: row for cid, row in old_chat.items()
                 if cid.startswith("multi-") and cid.endswith(("-2", "-3"))}
    new_multi = {cid: row for cid, row in chat.items() if cid in old_multi}
    if len(old_multi) != 24 or len(new_multi) != 24:
        raise ValueError("Expected all 24 multi-turn update follow-ups before and after")

    routes = Counter(row["response"]["rag"]["route"]["effective_mode"] for row in responses.values())
    db_used = sum(row["response"]["rag"]["database_context"]["used_for_chat"] for row in responses.values())
    rag_used = sum(row["response"]["rag"]["used_for_chat"] for row in responses.values())
    direct = sum(row["response"]["rag"].get("answer_method") == "structured_current_record"
                 for row in responses.values())
    mean_elapsed = sum(row["elapsed_seconds"] for row in responses.values()) / 180
    disagree = [cid for cid in cases if chat[cid]["scores"] != llama[cid]["scores"]
                or set(chat[cid]["critical_errors"]) != set(llama[cid]["critical_errors"])]
    missed_critical = sorted(cid for cid in cases if chat[cid]["critical_errors"]
                             and not llama[cid]["critical_errors"])
    old_chat_overlap = set(old_chat)
    old_llama_all_two = sum(all(v == 2 for v in row["verdict"]["scores"].values()) for row in old_llama.values())
    old_chat_overlap_critical = sum(bool(old_chat[cid]["critical_errors"]) for cid in old_chat_overlap)
    new_chat_overlap_critical = sum(bool(chat[cid]["critical_errors"]) for cid in old_chat_overlap)
    ls, cs = stats(llama), stats(chat)

    shared = f"""## Scope and method

- This is the **post-fix** cloud run. The original reports remain the pre-fix baseline. The runner created 36 new fictional patients, stored 180 case specifications in a temporary cloud PostgreSQL table, read each case back, mirrored the corresponding patient/CALD/medication/allergy fields, and sent 180 requests. Risk, task and medication-support fields were cloud-stored as case specifications and supplied to the endpoint; they were not separate normalized clinical rows.
- Cases cover six domains with 36 A baselines, 36 relevant B changes, 36 irrelevant C changes, 36 context-omitted controls and 36 turns from twelve three-turn conversations. The 24 update follow-ups used the `structured_current_record` path; the other replies used model generation.
- Every request returned HTTP 200. Cleanup deleted 36 patient rows and the temporary table; a separate read-only PostgreSQL query confirmed zero patient rows, zero batch rows and no case table. The saved fixture manifest records the batch ID and cleanup.
- Routes: {', '.join(f'{k} {v}' for k, v in sorted(routes.items()))}; database context used in {db_used}/180 responses; RAG used in {rag_used}/180. The answer method was structured for {direct}/180. Mean HTTP response time {mean_elapsed:.2f} seconds. The source Qdrant collection was `silvercare_knowledge`; no immutable collection snapshot was captured.
- Each applicable dimension uses the operational C3A 0–2 rubric: 2 meets the case expectation, 1 partly meets it, 0 misses or contradicts it. Critical tags are reported separately. Turn-one continuity is N/A because no prior answer exists. The scale was designed for this project; it is not a paper-validated clinical safety score. No clinician adjudication was performed.

"""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    llama_report = f"""# C3A 180-case post-fix evaluation — Llama3 judge

Generated {stamp}. This report scores **all 180 saved post-fix responses** with local `llama3:latest`. The generator and judge are the same local model, so the result is a self-judgment with known calibration false negatives.

{shared}## Llama3 results

- All applicable dimensions scored 2 in **{ls['all_two_cases']}/180** cases (pre-fix Llama3: {old_llama_all_two}/180); at least one dimension scored 0 in **{ls['zero_cases']}/180**; **{ls['critical_cases']}/180** were tagged critical.
- Dimension grades: 2 = {ls['grades'].get('2', 0)}, 1 = {ls['grades'].get('1', 0)}, 0 = {ls['grades'].get('0', 0)}, N/A = {ls['grades'].get('None', 0)}. Distinct-case critical tags: {dict(ls['critical_tags'])}.
- On the 24 multi-turn update follow-ups, **{sum(all(v == 2 for v in r['scores'].values()) for r in new_multi.values())}/24** received all-2 scores from the independent current-chat judge (pre-fix current-chat audit: {sum(all(v == 2 for v in r['scores'].values()) for r in old_multi.values())}/24). This cross-check is reported here to keep Llama3's apparent performance in perspective.

### By domain

{breakdown(llama, cases, 'domain')}

### By condition

{breakdown(llama, cases, 'condition')}

## Judge limitations and disagreement

Llama3 previously missed two known-bad calibration answers: medication-support completion described as medication administered, and a resolved falls alert introduced as active. It is unsuitable as the sole pass/fail authority. In this post-fix run, it disagreed with the full current-chat review on **{len(disagree)}/180** cases and failed to tag **{len(missed_critical)}** cases that the current-chat review marked critical. Direct current-record answers remove model generation from the 24 narrow update follow-ups, while other case families still expose generation errors.

The raw JSONL contains every score and reason. Exact retrieved evidence excerpts and citations are retained in the response log. Llama3's raw turn-one continuity scores are preserved there; this report treats those twelve scores as N/A.

## Files

- `c3a-core-ai/evaluation/results/cloud_full_after_refresh_{DATE}.jsonl` — requests and responses.
- `c3a-core-ai/evaluation/results/llama3_judge_full_after_refresh_{DATE}.jsonl` — all 180 raw Llama3 verdicts.
- `c3a-core-ai/evaluation/results/cloud_full_after_refresh_manifest_{DATE}.json` — cloud fixture and cleanup.
"""
    top_critical = sorted(cid for cid in chat if chat[cid]["critical_errors"])
    critical_lines = ["| Case | Current-chat critical tag(s) | Llama3 tag(s) |",
                      "|---|---|---|"]
    for cid in top_critical:
        critical_lines.append(f"| `{cid}` | {', '.join(chat[cid]['critical_errors'])} | {', '.join(llama[cid]['critical_errors']) or 'none'} |")
    chat_report = f"""# C3A 180-case post-fix evaluation — current-chat model review

Generated {stamp}. The current conversation model read and scored **all 180 saved post-fix responses** in blinded packets with opaque review IDs. The case specification, conversation, current structured context, reply, and retrieved evidence were available for review. The exact deployment ID and inference settings of this conversation model are not programmatically attested by the files.

{shared}## Current-chat results

- All applicable dimensions scored 2 in **{cs['all_two_cases']}/180** cases; at least one dimension scored 0 in **{cs['zero_cases']}/180**; **{cs['critical_cases']}/180** were tagged critical.
- Dimension grades: 2 = {cs['grades'].get('2', 0)}, 1 = {cs['grades'].get('1', 0)}, 0 = {cs['grades'].get('0', 0)}, N/A = {cs['grades'].get('None', 0)}. Distinct-case critical tags: {dict(cs['critical_tags'])}.
- All **24/24 multi-turn update follow-ups** received all-2 scores, compared with **{sum(all(v == 2 for v in r['scores'].values()) for r in old_multi.values())}/24** on the same cases before the fix. Pre-fix, {sum(bool(r['critical_errors']) for r in old_multi.values())}/24 follow-ups were tagged critical; post-fix, {sum(bool(r['critical_errors']) for r in new_multi.values())}/24. This comparison is paired and limited to the changed behavior.
- Across the {len(old_chat_overlap)} cases reviewed by this judge before the fix, critical tags changed from **{old_chat_overlap_critical}/{len(old_chat_overlap)}** to **{new_chat_overlap_critical}/{len(old_chat_overlap)}**. The pre-fix current-chat review did not cover all 180 cases, so there is no valid full-180 before/after comparison for this judge.

### By domain

{breakdown(chat, cases, 'domain')}

### By condition

{breakdown(chat, cases, 'condition')}

## Remaining failure patterns

- **Medication inference:** some generated answers turn a medicine merely listed in the record into a claim that the patient is taking it, or infer that declined support proves no medicine was administered. Other answers omit a recorded medication-support status while discussing a separate pending task.
- **Missing-record controls:** some answers treat absent context as proof no patient fact exists, or invent a patient condition and give patient-specific advice. The correct response is that the patient-specific answer cannot be determined from the supplied context.
- **Communication and evidence:** some answers miss a recorded interpreter requirement or turn an unknown interpreter flag into a definite “not required.” Some mobility advice cites retrieved delirium material that does not directly support the claim.
- The repaired multi-turn current-value path performs well on its 24 target follow-ups, but it does **not** prove the system can identify exact changes between two structured record versions. The request contains only the current structured snapshot.

### Critical cases, with Llama3 comparison

{chr(10).join(critical_lines)}

The judges differed on at least one dimension score or critical tag in **{len(disagree)}/180** cases. This is model-to-model disagreement, not clinician agreement. The raw current-chat JSONL provides each case's dimensions, reasons below 2 and critical tags.

## Interpretation

The targeted record-update failure is resolved in this test set, but the full run still shows patient-fact, uncertainty, communication and source-support errors. The system should not be described as clinically validated or generally safe based on these scores alone. The next engineering work should address the listed failure families and then repeat the affected controls and medication/communication cases.

## Files

- `c3a-core-ai/evaluation/results/inchat_judge_full_after_refresh_{DATE}.jsonl` — all 180 current-chat verdicts.
- `c3a-core-ai/evaluation/results/inchat_full_after_refresh_packets_{DATE}.jsonl` and `inchat_full_after_refresh_map_{DATE}.json` — blinded review packets and mapping.
- `c3a-core-ai/evaluation/results/cloud_full_after_refresh_{DATE}.jsonl` — original responses.
"""
    OUT.mkdir(exist_ok=True)
    (OUT / f"C3A_180_Llama3_After_Refresh_Report_{DATE}.md").write_text(llama_report)
    (OUT / f"C3A_180_InChat_After_Refresh_Report_{DATE}.md").write_text(chat_report)
    manifest = {
        "run_date": DATE,
        "responses": 180,
        "http_200": 180,
        "cloud_fixture_cleanup": fixture["cleanup"],
        "database_source": "c3a-core-ai/.env DATABASE_URL",
        "generator_model": "llama3:latest",
        "llama_judge_model": "llama3:latest",
        "llama_model_digest": "365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1",
        "current_chat_reviewed": len(chat),
        "routes": dict(routes),
        "db_used_for_chat": db_used,
        "rag_used_for_chat": rag_used,
        "structured_answers": direct,
        "qdrant_collection": "silvercare_knowledge",
        "qdrant_snapshot_hash": None,
        "sha256": {str(p.relative_to(ROOT)): file_hash(p) for p in (
            case_path, response_path, fixture_path, llama_path, chat_path, map_path,
            EVAL / "run_cloud_cases.py", EVAL / "judge_llama.py", EVAL / "judge_rubric.md",
            EVAL.parent / "main.py", EVAL.parent / "ollama_service.py")},
    }
    (OUT / f"C3A_180_After_Refresh_Manifest_{DATE}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"llama": ls, "current_chat": cs, "judge_disagreements": len(disagree),
                      "llama_missed_critical": len(missed_critical), "multi_followups_all2": 24}, default=dict, indent=2))


if __name__ == "__main__":
    main()
