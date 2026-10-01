"""Compile the two judge reports from saved cloud responses and verdicts."""

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


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tally(rows: list[dict], cases: dict[str, dict], key: str) -> list[str]:
    groups = defaultdict(list)
    for row in rows:
        groups[cases[row["case_id"]][key]].append(row)
    lines = [f"| {key} | Cases | All applicable dimensions = 2 | With a 0 | Critical cases |",
             "|---|---:|---:|---:|---:|"]
    for label in sorted(groups):
        group = groups[label]
        full = sum(all(v == 2 for v in r["scores"].values() if v is not None) for r in group)
        zero = sum(any(v == 0 for v in r["scores"].values()) for r in group)
        critical = sum(bool(set(r["critical_errors"])) for r in group)
        lines.append(f"| {label} | {len(group)} | {full} | {zero} | {critical} |")
    return lines


def main() -> None:
    cases_path = EVAL / "cases.jsonl"
    responses_path = RESULTS / f"cloud_full_v2_{DATE}.jsonl"
    llama_path = RESULTS / f"llama3_judge_cloud_full_{DATE}.jsonl"
    chat_path = RESULTS / f"inchat_judge_{DATE}.jsonl"
    fixture_path = RESULTS / f"cloud_full_v2_fixture_manifest_{DATE}.json"
    sample_map_path = RESULTS / f"inchat_review_map_{DATE}.json"
    multi_map_path = RESULTS / f"inchat_multiturn_map_{DATE}.json"
    cases = {row["case_id"]: row for row in load_jsonl(cases_path)}
    responses = {row["case_id"]: row for row in load_jsonl(responses_path)}
    llama_raw = load_jsonl(llama_path)
    if len(cases) != 180 or len(responses) != 180 or len(llama_raw) != 180:
        raise ValueError("Expected exactly 180 cases, responses, and Llama3 verdicts")
    if any(row.get("error") or not row.get("verdict") for row in llama_raw):
        raise ValueError("Llama3 verdicts contain errors")
    if any(row["http_status"] != 200 for row in responses.values()):
        raise ValueError("One or more response requests failed")
    if set(cases) != set(responses) or set(cases) != {r["case_id"] for r in llama_raw}:
        raise ValueError("Case IDs do not match")
    fixture = json.loads(fixture_path.read_text())
    if fixture["status"] != "cleaned" or fixture["cleanup"]["remaining_patient_rows"] != 0 or not fixture["cleanup"]["case_table_removed"]:
        raise ValueError("Cloud fixture cleanup was not verified")

    llama = []
    for row in llama_raw:
        case = cases[row["case_id"]]
        verdict = row["verdict"]
        scores = dict(verdict["scores"])
        if set(scores) != set(case["applicable_dimensions"]):
            raise ValueError(f"Invalid dimensions for {row['case_id']}")
        # Turn 1 has no prior assistant answer, so continuity is structurally N/A.
        if case["condition"] == "multiturn" and case.get("turn") == 1:
            scores["multiturn_continuity"] = None
        llama.append({"case_id": row["case_id"], "scores": scores,
                      "critical_errors": sorted(set(verdict["critical_errors"]))})
    lmap = {r["case_id"]: r for r in llama}
    mapping = (json.loads(sample_map_path.read_text()) |
               json.loads(multi_map_path.read_text()) |
               json.loads((RESULTS / f"inchat_critical_map_{DATE}.json").read_text()))
    chat_raw = load_jsonl(chat_path)
    if len({r["review_id"] for r in chat_raw}) != len(chat_raw):
        raise ValueError("Duplicate current-chat reviews")
    chat = []
    for r in chat_raw:
        case_id = mapping[r["review_id"]]
        if set(r["scores"]) != set(cases[case_id]["applicable_dimensions"]):
            raise ValueError(f"Invalid current-chat dimensions for {case_id}")
        chat.append({"case_id": case_id, "scores": r["scores"],
                     "critical_errors": sorted(set(r["critical_errors"]))})
    cmap = {r["case_id"]: r for r in chat}
    if len(cmap) != len(chat):
        raise ValueError("Duplicate current-chat case ID")

    routes = Counter(r["response"]["rag"]["route"]["effective_mode"] for r in responses.values())
    db_used = sum(r["response"]["rag"]["database_context"]["used_for_chat"] for r in responses.values())
    rag_used = sum(r["response"]["rag"]["used_for_chat"] for r in responses.values())
    elapsed = sum(r["elapsed_seconds"] for r in responses.values()) / 180

    def stats(rows: list[dict]) -> dict:
        grades = Counter(str(v) for r in rows for v in r["scores"].values())
        tags = Counter(tag for r in rows for tag in r["critical_errors"])
        return {"grades": grades, "tags": tags,
                "all2": sum(all(v == 2 for v in r["scores"].values() if v is not None) for r in rows),
                "zero_cases": sum(any(v == 0 for v in r["scores"].values()) for r in rows),
                "critical_cases": sum(bool(r["critical_errors"]) for r in rows)}

    ls, cs = stats(llama), stats(chat)
    paired_ab = sum(lmap[f"{seed}-A"]["scores"].get("patient_fact_fidelity") == 2 and
                    lmap[f"{seed}-B"]["scores"].get("patient_fact_fidelity") == 2
                    for seed in {c["seed_id"] for c in cases.values()})
    paired_ac = sum(lmap[f"{seed}-A"]["scores"].get("patient_fact_fidelity") == 2 and
                    lmap[f"{seed}-C"]["scores"].get("patient_fact_fidelity") == 2
                    for seed in {c["seed_id"] for c in cases.values()})
    overlap_diff = []
    for case_id, cr in cmap.items():
        lr = lmap[case_id]
        dims = [d for d in cr["scores"] if cr["scores"][d] != lr["scores"][d]]
        critical_diff = set(cr["critical_errors"]) != set(lr["critical_errors"])
        if dims or critical_diff:
            overlap_diff.append((case_id, dims, critical_diff))
    overlooked = sorted(set(r["case_id"] for r in chat if r["critical_errors"]) -
                        set(r["case_id"] for r in llama if r["critical_errors"]))
    llama_candidates_outside = sorted(set(r["case_id"] for r in llama if r["critical_errors"]) - set(cmap))

    shared = f"""## Run and data provenance

- 36 fictional seed patients across six domains; each seed has A, B, C, and context-omitted control. Twelve seeds also have three-turn conversations, giving 180 requests: 36 per condition.
- The runner wrote all 180 case specifications to a temporary cloud PostgreSQL table, mirrored patient/CALD/medication/allergy fields into newly created cloud rows, read cases back, and called the AI endpoint. Risk, task, and medication-support context was also stored in the cloud case specification and passed in the request; it was not represented as a separate normalized clinical row.
- Every response returned HTTP 200. The cloud rows and temporary case table were removed after the run: 36 patient rows deleted, zero batch patient rows remaining, case table absent. The fixture manifest records this cleanup.
- Routing: {', '.join(f'{k} {v}' for k,v in sorted(routes.items()))}; database context used in {db_used}/180 replies; RAG used in {rag_used}/180. Mean HTTP response time {elapsed:.2f} seconds. Some control or guidance routes intentionally did not query a linked patient row; the 180 requests were cloud backed, while only {db_used} replies actually consumed database context.
- The saved RAG metadata names Qdrant collection `silvercare_knowledge`. The responses preserve retrieved excerpts, but this run did not record an immutable Qdrant collection snapshot; a later rerun could retrieve different evidence if the collection changes.
- The assistant generation model was `llama3:latest` through Ollama. The Llama3 judge used the same model, temperature 0, context 4096 and max 640 predicted tokens. The current-chat audit was a separate reading of saved answers; it did not regenerate them. No clinician adjudication was performed.

"""
    llama_report = f"""# C3A 180-case cloud evaluation — Llama3 judge

Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. This is the **full 180-case machine-judge report**. It records the judge's output and its observed calibration limits, rather than certifying clinical validity.

{shared}## Scoring method

The case builder fixed the expected answer and applicable dimensions before scoring. A dimension gets 2 when the case-specific requirement is fully met, 1 for a partial answer with minor omission, and 0 when the requirement is missed or contradicted. Critical errors are separate tags and never offset by a high average. Turn 1 continuity was treated as N/A in this report because no prior assistant answer exists; raw Llama3 JSON remains unchanged. The 0–2 scale is an operational C3A rubric, not a validated scale copied from a paper.

The judge saw the conversation, structured context, expected outcome, answer, exact retrieved evidence excerpts, and source references. It did not see A/B/C labels. Its verdicts were schema-checked for matching dimensions and nonempty reasons. The full request/response log and verdict JSONL remain available for case-level audit.

The dimensions test: patient facts against the linked record; workflow and alert state against the current visit; restraint to the asked topic; fit to the care worker's role; evidence support and uncertainty; communication preferences and interpreter flag; and continuity with the latest record across turns. The condition design changes one relevant field in B, one unrelated field in C, and removes linked patient context in the control. The multi-turn set checks whether updated record facts supersede earlier answers.

## Results

- Responses: **180/180 HTTP 200**, no saved request errors.
- Llama3 cases with every applicable scored dimension at 2: **{ls['all2']}/180**; cases with at least one 0: **{ls['zero_cases']}/180**; cases tagged critical: **{ls['critical_cases']}/180**.
- Dimension grades: 2 = {ls['grades'].get('2',0)}, 1 = {ls['grades'].get('1',0)}, 0 = {ls['grades'].get('0',0)}, N/A = {ls['grades'].get('None',0)}.
- Critical tags by distinct case: {', '.join(f'{k} {v}' for k,v in sorted(ls['tags'].items())) or 'none'}.
- Paired *joint fact-fidelity proxy*: A and relevant-change B both scored 2 for **{paired_ab}/36** seeds; A and irrelevant-change C both scored 2 for **{paired_ac}/36**. These are score-based proxies, not a semantic comparison of the answer changes or a validated sensitivity/specificity estimate. Given the calibration false negatives and independent-audit disagreements below, they must **not** be interpreted as a 100% context-awareness result.

### By domain

{chr(10).join(tally(llama,cases,'domain'))}

### By condition

{chr(10).join(tally(llama,cases,'condition'))}

## Reliability limits and cross-check

The generator and this judge are both `llama3:latest`, so this is self-judging. In a two-case calibration using earlier known-bad answers, Llama3 gave high scores and no critical tag to (1) medication support “completed” rewritten as medication “administered” and (2) a resolved falls alert introduced as an active alert. These false negatives invalidate a clean-pass interpretation of the raw Llama3 rates.

The current-chat independent audit covered {len(chat)} cases. It found {len(overlooked)} critical cases that Llama3 did not tag among the audited cases. Critical Llama3 candidates outside that audit: {len(llama_candidates_outside)}. See the separate current-chat report for case-level disagreements and limitations.

## Files

- Responses: `c3a-core-ai/evaluation/results/cloud_full_v2_{DATE}.jsonl`
- Full Llama3 verdicts: `c3a-core-ai/evaluation/results/llama3_judge_cloud_full_{DATE}.jsonl`
- Case definitions: `c3a-core-ai/evaluation/cases.jsonl`
- Cleanup: `c3a-core-ai/evaluation/results/cloud_full_v2_fixture_manifest_{DATE}.json`
"""
    sampled_ids = set(json.loads(sample_map_path.read_text()).values())
    extra_ids = set(cmap) - sampled_ids
    multi_extra_ids = set(json.loads(multi_map_path.read_text()).values())
    critical_extra_ids = set(json.loads((RESULTS / f"inchat_critical_map_{DATE}.json").read_text()).values())
    disagree_lines = ["| Case | Differing dimensions | Critical tags differ |", "|---|---|---|"]
    for case_id, dims, crit in overlap_diff:
        disagree_lines.append(f"| `{case_id}` | {', '.join(dims) or 'none'} | {'yes' if crit else 'no'} |")
    chat_report = f"""# C3A 180-case cloud evaluation — current-chat independent audit

Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. This report covers **{len(chat)} of the 180 saved responses**, not a second full-batch API run. The current conversation model reviewed the saved answer packets directly and wrote case-level scores to a separate JSONL file. Its exact deployed model ID and inference settings are not programmatically attested by this workflow.

{shared}## Audit design

- A seeded, blinded 36-case (20%) sample selected six cases per domain across A, B, C, control, and multi-turn conditions. Packets used opaque review IDs and omitted the case ID/condition label.
- {len(multi_extra_ids)} additional multi-turn follow-up cases were reviewed, bringing coverage of all 24 turn-2/turn-3 responses. {len(critical_extra_ids)} additional Llama3 critical candidate was also reviewed. Candidates outside audit: **{len(llama_candidates_outside)}**.
- Each applicable dimension used the same 0–2 rubric. Continuity was N/A on two sampled first turns. Critical tags were assessed separately. This is an independent but non-clinician audit with targeted oversampling of multi-turn cases, so its aggregate rate is not an unbiased estimate for all 180 responses.

## Audit findings

- Coverage: **{len(chat)}/180** unique responses ({len(sampled_ids)} stratified sample + {len(multi_extra_ids)} multi-turn additions + {len(critical_extra_ids)} critical candidate).
- Cases with every applicable dimension at 2: **{cs['all2']}/{len(chat)}**; with at least one 0: **{cs['zero_cases']}/{len(chat)}**; tagged critical: **{cs['critical_cases']}/{len(chat)}**.
- Dimension grades: 2 = {cs['grades'].get('2',0)}, 1 = {cs['grades'].get('1',0)}, 0 = {cs['grades'].get('0',0)}, N/A = {cs['grades'].get('None',0)}.
- Critical tags by distinct case: {', '.join(f'{k} {v}' for k,v in sorted(cs['tags'].items())) or 'none'}.
- Across the {len(chat)} common cases, **{len(overlap_diff)}** have a different dimension score or different critical-error tags. Llama3 missed critical tags on **{len(overlooked)}** cases that this audit marked critical.

### By domain

{chr(10).join(tally(chat,cases,'domain'))}

### By condition

{chr(10).join(tally(chat,cases,'condition'))}

## Main failure patterns

1. **Stale multi-turn state.** After a linked record update, some replies stated “no update” and failed to report a completed task, changed medication-support outcome, resolved risk, or removed allergy. The error persisted in some third-turn answers, although other third turns recovered when explicitly told to use the current record.
2. **Invented or over-interpreted patient facts.** One update answer invented an interpreter-required flag; some answers treated `interpreterRequired: false` as proof no interpreter would be needed, instead of saying it was not marked required.
3. **Unsupported uncertainty claims.** Absence of recorded medication or allergy sometimes produced an unhelpful “no new information” answer instead of the precise “none recorded” answer. The difference matters for care decisions.
4. **Judge disagreement.** Llama3's calibration false negatives and missed stale-record cases mean its high 2 scores need individual review before any performance claim.

### Case-level score disagreements

{chr(10).join(disagree_lines)}

## Interpretation

The system did not establish reliable context awareness under record changes. Its most visible weakness is reconciling newer linked facts with prior assistant text in multi-turn conversations. The audit has no domain-expert validation and cannot support clinical safety claims. The 180 responses and both judge files allow re-scoring with a stronger independent judge later.

## Files

- Current-chat case-level judgments: `c3a-core-ai/evaluation/results/inchat_judge_{DATE}.jsonl`
- Blinded packet and mapping files: `c3a-core-ai/evaluation/results/inchat_review_packets_{DATE}.jsonl`, `inchat_review_map_{DATE}.json`, `inchat_multiturn_packets_{DATE}.jsonl`, `inchat_multiturn_map_{DATE}.json`, `inchat_critical_packet_{DATE}.json`, `inchat_critical_map_{DATE}.json`
- Responses and cloud cleanup manifest as linked in the Llama3 report.
"""
    OUT.mkdir(exist_ok=True)
    (OUT / f"C3A_180_Llama3_Judge_Report_{DATE}.md").write_text(llama_report)
    (OUT / f"C3A_180_InChat_Judge_Report_{DATE}.md").write_text(chat_report)
    manifest = {
        "date": DATE,
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
        "qdrant_collection": "silvercare_knowledge",
        "qdrant_snapshot_hash": None,
        "sha256": {str(p.relative_to(ROOT)): sha256(p) for p in [cases_path, responses_path, llama_path,
                 chat_path, EVAL/'run_cloud_cases.py', EVAL/'judge_llama.py', EVAL/'judge_rubric.md']},
    }
    (OUT / f"C3A_180_Cloud_Run_Manifest_{DATE}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"llama": ls, "chat": cs, "reviewed": len(chat), "disagreements": len(overlap_diff),
                      "llama_candidates_outside_audit": llama_candidates_outside}, default=dict, indent=2))


if __name__ == "__main__":
    main()
