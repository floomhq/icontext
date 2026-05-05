#!/usr/bin/env python3
"""Evaluate fbrain retrieval against explicit query/path cases."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from indexlib import search


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_any: tuple[str, ...]


def load_cases(path: Path) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for item in data:
        query = str(item["query"])
        expected = tuple(str(path) for path in item["expected_any"])
        if not expected:
            raise ValueError(f"eval case has no expected paths: {query}")
        cases.append(EvalCase(query=query, expected_any=expected))
    return cases


def evaluate(repo: Path, cases: list[EvalCase], limit: int) -> tuple[int, list[dict]]:
    failures = 0
    rows: list[dict] = []
    for case in cases:
        results = search(repo, case.query, limit=limit)
        paths = [result.path for result in results]
        hit = any(expected in paths for expected in case.expected_any)
        if not hit:
            failures += 1
        rows.append(
            {
                "query": case.query,
                "expected_any": list(case.expected_any),
                "top_paths": paths,
                "hit": hit,
            }
        )
    return failures, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    cases = load_cases(Path(args.cases).expanduser().resolve())
    failures, rows = evaluate(repo, cases, args.limit)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            status = "PASS" if row["hit"] else "FAIL"
            print(f"{status} {row['query']}")
            print(f"  expected_any: {', '.join(row['expected_any'])}")
            print(f"  top_paths: {', '.join(row['top_paths'])}")
        print(f"summary: {len(rows) - failures} pass, {failures} fail")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
