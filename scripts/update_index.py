#!/usr/bin/env python3
"""Update the local icontext search index."""

from __future__ import annotations

import argparse

from indexlib import rebuild


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    indexed = rebuild(args.repo)
    print(f"icontext: indexed {indexed} text file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
