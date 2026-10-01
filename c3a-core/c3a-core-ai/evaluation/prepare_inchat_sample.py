"""Select a blinded 20% audit or all saved replies for current-chat review."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=HERE / "cases.jsonl")
    parser.add_argument("--seed", type=int, default=6015)
    parser.add_argument("--all", action="store_true", help="Prepare all 180 replies for a full second review")
    parser.add_argument("--namespace", default="c3a-inchat-audit", help="Opaque review-ID namespace")
    args = parser.parse_args()
    if args.packets.exists() or args.map.exists():
        raise SystemExit("Refusing to overwrite review packets or map")
    cases = {row["case_id"]: row for row in rows(args.cases)}
    results = {row["case_id"]: row for row in rows(args.results)}
    if len(cases) != 180 or len(results) != 180:
        raise ValueError("Expected a complete 180-case run")
    rng = random.Random(args.seed)
    if args.all:
        selected = sorted(cases)
    else:
        by_domain_condition: dict[tuple[str, str], list[str]] = defaultdict(list)
        for case_id, case in cases.items():
            by_domain_condition[(case["domain"], case["condition"])].append(case_id)
        selected = []
        for domain in sorted({case["domain"] for case in cases.values()}):
            for condition in ("A", "B", "C", "control", "multiturn"):
                selected.append(rng.choice(sorted(by_domain_condition[(domain, condition)])))
            other_b = [case_id for case_id in by_domain_condition[(domain, "B")] if case_id not in selected]
            selected.append(rng.choice(sorted(other_b)))
    rng.shuffle(selected)
    expected_count = 180 if args.all else 36
    if len(selected) != expected_count or len(set(selected)) != expected_count:
        raise AssertionError(f"Review selection must contain {expected_count} unique cases")
    mapping: dict[str, str] = {}
    packets: list[dict] = []
    for case_id in selected:
        opaque_id = hashlib.sha256((args.namespace + ":" + case_id).encode()).hexdigest()[:12]
        mapping[opaque_id] = case_id
        case, result = cases[case_id], results[case_id]
        answer = result["response"]
        packets.append({
            "review_id": opaque_id,
            "conversation": result["request"]["messages"],
            "context": {key: value for key, value in result["request"].items() if key != "messages"},
            "expected": case["expected"],
            "dimensions": case["applicable_dimensions"],
            "answer": answer["reply"],
            "evidence": [
                {"label": f"Source {index}", "title": item.get("source_title"),
                 "excerpt": item.get("evidence_excerpt")}
                for index, item in enumerate(answer.get("rag", {}).get("results", []), start=1)
            ],
            "source_references": answer.get("sourceReferences", []),
        })
    args.packets.parent.mkdir(parents=True, exist_ok=True)
    args.packets.write_text("".join(json.dumps(packet, ensure_ascii=False) + "\n" for packet in packets), encoding="utf-8")
    args.map.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    print(f"Selected {expected_count} blinded cases for current-chat review")


if __name__ == "__main__":
    main()
