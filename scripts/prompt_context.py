#!/usr/bin/env python3
"""Claude UserPromptSubmit hook for retrieving relevant context."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from indexlib import search


def _prompt(payload: dict) -> str:
    for key in ("prompt", "message", "user_prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = tool_input.get("prompt")
        if isinstance(value, str):
            return value
    return ""


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    repo = Path(os.environ.get("ICONTEXT_VAULT", "/Users/federicodeponte/context"))
    prompt = _prompt(payload)
    context = ""

    if prompt and repo.exists():
        results = search(repo, prompt, limit=5)
        if results:
            lines = ["Relevant context from icontext:"]
            for result in results:
                lines.append(f"- {result.path} [{result.tier}]: {result.snippet}")
            context = "\n".join(lines)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
