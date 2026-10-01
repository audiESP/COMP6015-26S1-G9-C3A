"""Validate draft case counts, pairing, and request structure without inference."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from build_cases import DOMAINS, SPECS


CASES_PATH = Path(__file__).with_name("cases.jsonl")


def leaf_diffs(left, right, prefix="") -> set[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        paths = set()
        for key in left.keys() | right.keys():
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                paths.add(path)
            else:
                paths |= leaf_diffs(left[key], right[key], path)
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return {prefix}
        paths = set()
        for index, (a, b) in enumerate(zip(left, right)):
            paths |= leaf_diffs(a, b, f"{prefix}.{index}")
        return paths
    return {prefix} if left != right else set()


def main() -> None:
    cases = [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line]
    assert len(cases) == 180, len(cases)
    assert len({c["case_id"] for c in cases}) == 180
    counts = Counter(c["condition"] for c in cases)
    assert counts == {"A": 36, "B": 36, "C": 36, "control": 36, "multiturn": 36}, counts
    groups = defaultdict(dict)
    for case in cases:
        assert case["domain"] in DOMAINS
        assert case["request"]["messages"][-1]["role"] == "user"
        if case["condition"] != "multiturn":
            groups[case["seed_id"]][case["condition"]] = case
    assert len(groups) == len(SPECS) == 36
    for group in groups.values():
        assert set(group) == {"A", "B", "C", "control"}
        a, b, c = (group[k] for k in ("A", "B", "C"))
        assert a["request"]["messages"] == b["request"]["messages"] == c["request"]["messages"]
        relevant_diffs = leaf_diffs(a["request"], b["request"])
        irrelevant_diffs = leaf_diffs(a["request"], c["request"])
        assert relevant_diffs and all(
            path == a["relevant_change_path"] or path.startswith(a["relevant_change_path"] + ".")
            for path in relevant_diffs
        ), a["case_id"]
        assert irrelevant_diffs and all(
            path == a["irrelevant_change_path"] or path.startswith(a["irrelevant_change_path"] + ".")
            for path in irrelevant_diffs
        ), a["case_id"]
        control = group["control"]["request"]
        assert "patientContext" not in control and "visitContext" not in control
    sequences = defaultdict(list)
    for case in cases:
        if case["condition"] == "multiturn":
            sequences[case["sequence_id"]].append(case)
    assert len(sequences) == 12
    assert all(sorted(c["turn"] for c in seq) == [1, 2, 3] for seq in sequences.values())
    print("Validated 36 triplets, 36 controls, 12 three-turn sequences, and 180 request specifications.")
    print("Case domains:", dict(Counter(c["domain"] for c in cases)))


if __name__ == "__main__":
    main()
