#!/usr/bin/env python3
"""Check changed files against icontext tier placement."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from icontext_classify import TIERS, classify


ZERO_SHA_RE = re.compile(r"^0{40}$")


def _run_git(args: list[str], repo: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "1", "on"}


def load_config(path: Path) -> tuple[dict[str, tuple[int, tuple[str, ...]]], bool]:
    tiers: dict[str, tuple[int, tuple[str, ...]]] = {}
    enforce_unclassified = False
    current_tier: str | None = None
    current_rank: int | None = None
    current_paths: list[str] = []
    in_tiers = False
    in_paths = False

    if not path.exists():
        raise FileNotFoundError(f"tier config not found: {path}")

    def flush() -> None:
        nonlocal current_tier, current_rank, current_paths, in_paths
        if current_tier is not None:
            if current_rank is None:
                raise ValueError(f"missing rank for tier {current_tier}")
            tiers[current_tier] = (current_rank, tuple(current_paths))
        current_tier = None
        current_rank = None
        current_paths = []
        in_paths = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if indent == 0 and stripped.startswith("enforce_unclassified_paths:"):
            enforce_unclassified = _parse_bool(stripped.split(":", 1)[1])
            continue

        if indent == 0 and stripped == "tiers:":
            in_tiers = True
            continue

        if in_tiers and indent == 2 and stripped.endswith(":"):
            flush()
            current_tier = stripped[:-1]
            continue

        if current_tier and indent == 4 and stripped.startswith("rank:"):
            current_rank = int(stripped.split(":", 1)[1].strip())
            continue

        if current_tier and indent == 4 and stripped == "paths:":
            in_paths = True
            continue

        if current_tier and in_paths and indent == 6 and stripped.startswith("- "):
            current_paths.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        raise ValueError(f"unsupported config line: {raw}")

    flush()

    if not tiers:
        raise ValueError(f"no tiers configured in {path}")

    return tiers, enforce_unclassified


def tier_for_path(path: str, tiers: dict[str, tuple[int, tuple[str, ...]]]) -> str | None:
    normalized = path.replace("\\", "/")
    matches: list[tuple[int, str]] = []
    for name, (_rank, prefixes) in tiers.items():
        for prefix in prefixes:
            if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
                matches.append((len(prefix), name))
    if not matches:
        return None
    return max(matches)[1]


def changed_files(repo: Path, ref_pairs: list[tuple[str, str]]) -> list[str]:
    files: set[str] = set()

    if not ref_pairs:
        output = _run_git(["diff", "--name-only", "--diff-filter=ACMR", "HEAD"], repo)
        return [line for line in output.splitlines() if line]

    for local_sha, remote_sha in ref_pairs:
        if ZERO_SHA_RE.match(local_sha):
            continue
        if ZERO_SHA_RE.match(remote_sha):
            output = _run_git(["ls-tree", "-r", "--name-only", local_sha], repo)
        else:
            output = _run_git(
                ["diff", "--name-only", "--diff-filter=ACMR", f"{remote_sha}..{local_sha}"],
                repo,
            )
        files.update(line for line in output.splitlines() if line)

    return sorted(files)


def tracked_files(repo: Path) -> list[str]:
    output = _run_git(["ls-files", "-z"], repo)
    return [item for item in output.split("\0") if item]


def check_paths(repo: Path, config: Path, paths: list[str]) -> int:
    tiers, enforce_unclassified = load_config(config)
    failures: list[str] = []
    warnings: list[str] = []
    skipped_unclassified = 0

    for rel_path in paths:
        if not (repo / rel_path).exists():
            continue

        placement = tier_for_path(rel_path, tiers)
        classification = classify(rel_path, repo)
        if placement is None:
            if enforce_unclassified:
                failures.append(
                    f"{rel_path}: classified {classification.tier} but path is outside "
                    "configured tier roots"
                )
            else:
                skipped_unclassified += 1
            continue

        placement_rank = tiers[placement][0]
        if classification.rank > placement_rank:
            failures.append(
                f"{rel_path}: classified {classification.tier} but placed in {placement} "
                f"(reasons: {', '.join(classification.reasons)})"
            )

    if warnings:
        print("icontext: tier warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"  - {warning}", file=sys.stderr)

    if failures:
        print("icontext: sensitivity tier check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    if skipped_unclassified:
        print(
            "icontext: sensitivity tier check passed for "
            f"{len(paths)} file(s); skipped {skipped_unclassified} unclassified "
            "legacy path(s)"
        )
    else:
        print(f"icontext: sensitivity tier check passed for {len(paths)} file(s)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--config", default=".icontext-tiers.yml")
    parser.add_argument("--ref-pair", action="append", default=[], metavar="LOCAL..REMOTE")
    parser.add_argument("--all", action="store_true", help="check all tracked files")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv[1:])

    repo = Path(args.repo).resolve()
    config = (repo / args.config).resolve()
    ref_pairs: list[tuple[str, str]] = []

    for pair in args.ref_pair:
        if ".." not in pair:
            parser.error(f"invalid --ref-pair {pair!r}; expected LOCAL..REMOTE")
        local_sha, remote_sha = pair.split("..", 1)
        ref_pairs.append((local_sha, remote_sha))

    paths = tracked_files(repo) if args.all else args.paths or changed_files(repo, ref_pairs)
    return check_paths(repo, config, paths)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
