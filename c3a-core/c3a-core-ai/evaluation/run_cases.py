"""Collect C3A answers for the prepared cases when explicitly requested.

The default invocation is an offline dry run. No network request is made unless
--execute is supplied. This script does not judge answers or compute scores.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


DEFAULT_CASES = Path(__file__).with_name("cases.jsonl")


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def run_units(cases: list[dict], seed: int) -> list[list[dict]]:
    units = [[case] for case in cases if case["condition"] != "multiturn"]
    sequences = defaultdict(list)
    for case in cases:
        if case["condition"] == "multiturn":
            sequences[case["sequence_id"]].append(case)
    units.extend(sorted(sequence, key=lambda case: case["turn"]) for sequence in sequences.values())
    random.Random(seed).shuffle(units)
    return units


def execute(units: list[list[dict]], endpoint: str, output: Path, timeout: float) -> None:
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing result file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with output.open("x", encoding="utf-8") as stream:
        for unit in units:
            history = []
            for case in unit:
                request = copy.deepcopy(case["request"])
                if case["condition"] == "multiturn":
                    request["messages"] = history + request["messages"]
                started = time.monotonic()
                result = {
                    "case_id": case["case_id"],
                    "seed_id": case["seed_id"],
                    "condition": case["condition"],
                    "sequence_id": case.get("sequence_id"),
                    "turn": case.get("turn"),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "request": request,
                }
                try:
                    response = requests.post(endpoint, json=request, timeout=timeout)
                    result["http_status"] = response.status_code
                    if response.ok:
                        result["response"] = response.json()
                        if case["condition"] == "multiturn":
                            history = request["messages"] + [
                                {"role": "assistant", "content": result["response"]["reply"]}
                            ]
                    else:
                        result["error"] = response.text[:500]
                except requests.RequestException as exc:
                    result["error"] = type(exc).__name__
                result["elapsed_seconds"] = round(time.monotonic() - started, 3)
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                stream.flush()
                completed += 1
                print(f"{completed}/180 {case['case_id']} HTTP {result.get('http_status')} error {result.get('error')}", flush=True)
                if "error" in result and case["condition"] == "multiturn":
                    break


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--seed", type=int, default=6015)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8001/ai/chat")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true", help="Actually send all prepared requests")
    args = parser.parse_args()
    cases = load_cases(args.cases)
    units = run_units(cases, args.seed)
    print("cases:", len(cases), "units:", len(units), "conditions:", dict(Counter(x["condition"] for x in cases)))
    if not args.execute:
        print("Dry run only: no AI requests sent. Pass --execute and --output for the formal collection.")
        return
    if args.output is None:
        parser.error("--output is required with --execute")
    execute(units, args.endpoint, args.output, args.timeout)


if __name__ == "__main__":
    main()
