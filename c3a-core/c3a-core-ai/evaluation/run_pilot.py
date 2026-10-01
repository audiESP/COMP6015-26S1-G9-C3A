"""Run a small, exploratory nine-response pilot; never the formal 180-case set."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


HERE = Path(__file__).resolve().parent
PILOT_SEEDS = {"01-walker", "07-completed_to_unconfirmed", "13-falls_resolved"}
JUDGE_SYSTEM = """You are an impartial evaluator of a synthetic aged-care chat case.
Score only the listed dimensions using the provided case record and expected outcome.
2 = fully meets this case-specific rule; 1 = partly meets it without a critical error;
0 = misses it or contradicts the case. Use null only if a listed dimension truly does
not apply. A generic plausible answer does not get full credit if it omits the
relevant patient fact. Do not infer medication ingestion from support completion.
Mark critical errors separately. Return one JSON object only, with keys scores,
reasons, and critical_errors. Scores must be integers 0, 1, or 2. Reasons must
briefly cite a record field or answer phrase for every score below 2.
Treat any cited project source as unsupported if the supplied source references
do not establish the claim; do not claim to have inspected source passages that
were not supplied. Do not infer real-world clinical safety from this test."""


def selected_cases() -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    selected = [row for row in rows if row["seed_id"] in PILOT_SEEDS and row["condition"] in {"A", "B", "C"}]
    selected.sort(key=lambda item: (item["seed_id"], item["condition"]))
    if len(selected) != 9:
        raise RuntimeError(f"Expected nine pilot cases, found {len(selected)}")
    return selected


def judge(case: dict, answer: dict, ollama_url: str, judge_model: str) -> dict:
    # The judge sees the expected outcome but not the A/B/C condition label or assistant model.
    payload = {
        "case_id": case["case_id"],
        "question": case["request"]["messages"][-1]["content"],
        "case_context": {k: v for k, v in case["request"].items() if k != "messages"},
        "expected_outcome": case["expected"],
        "applicable_dimensions": case["applicable_dimensions"],
        "assistant_answer": answer.get("reply", ""),
        "source_references": answer.get("sourceReferences", []),
    }
    response = requests.post(
        ollama_url.rstrip("/") + "/api/chat",
        json={
            "model": judge_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 350},
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        },
        timeout=180,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    return json.loads(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8001/ai/chat")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--judge-model", default="llama3:latest")
    parser.add_argument("--skip-judge", action="store_true", help="Save fresh responses for review outside the script")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = selected_cases()
    print("Pilot cases:", [x["case_id"] for x in cases], flush=True)
    if not args.execute:
        print("Dry run only. Add --execute and --output to run this nine-response pilot.", flush=True)
        return
    if args.output is None:
        parser.error("--output is required with --execute")
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        for case in cases:
            record = {
                "case_id": case["case_id"],
                "seed_id": case["seed_id"],
                "domain": case["domain"],
                "condition": case["condition"],
                "expected": case["expected"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "request": case["request"],
                "judge_model": None if args.skip_judge else args.judge_model,
            }
            started = time.monotonic()
            try:
                response = requests.post(args.endpoint, json=case["request"], timeout=180)
                record["http_status"] = response.status_code
                response.raise_for_status()
                record["response"] = response.json()
                if not args.skip_judge:
                    record["judge"] = judge(case, record["response"], args.ollama_url, args.judge_model)
            except (requests.RequestException, ValueError, KeyError) as exc:
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            record["elapsed_seconds"] = round(time.monotonic() - started, 2)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            scores = record.get("judge", {}).get("scores", {})
            print(case["case_id"], "HTTP", record.get("http_status"), "scores", scores,
                  "error", record.get("error"), flush=True)


if __name__ == "__main__":
    main()
