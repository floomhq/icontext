#!/usr/bin/env python3
"""Minimal local index updater.

This creates a timestamp marker so post-commit has a concrete, testable action.
The semantic index implementation can replace this file without changing hooks.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    state_dir = repo / ".git" / "icontext"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "last-indexed").write_text(
        datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ\n"),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

