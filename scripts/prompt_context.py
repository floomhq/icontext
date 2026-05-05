#!/usr/bin/env python3
"""Claude UserPromptSubmit hook for retrieving relevant context."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from indexlib import search

DEFAULT_MAX_TIER = "internal"
DEFAULT_CHAR_BUDGET = 1500
DEFAULT_LIMIT = 5


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


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "")
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    repo = Path(os.environ.get("FBRAIN_VAULT") or os.environ.get("ICONTEXT_VAULT", str(Path("~/context").expanduser())))
    max_tier = (os.environ.get("FBRAIN_MAX_TIER") or os.environ.get("ICONTEXT_MAX_TIER", DEFAULT_MAX_TIER)).strip().lower() or DEFAULT_MAX_TIER
    char_budget = _int_env("FBRAIN_PROMPT_CHAR_BUDGET", DEFAULT_CHAR_BUDGET, 0, 6000)
    if "FBRAIN_PROMPT_CHAR_BUDGET" not in os.environ:
        char_budget = _int_env("ICONTEXT_PROMPT_CHAR_BUDGET", DEFAULT_CHAR_BUDGET, 0, 6000)
    limit = _int_env("FBRAIN_PROMPT_LIMIT", DEFAULT_LIMIT, 1, 10)
    if "FBRAIN_PROMPT_LIMIT" not in os.environ:
        limit = _int_env("ICONTEXT_PROMPT_LIMIT", DEFAULT_LIMIT, 1, 10)
    prompt = _prompt(payload)
    context = ""

    if prompt and repo.exists() and char_budget:
        results = search(repo, prompt, limit=limit, max_tier=max_tier)
        if results:
            lines = ["Relevant context from fbrain:"]
            used_chars = len(lines[0])
            seen_paths: set[str] = set()
            for result in results:
                if result.path in seen_paths:
                    continue
                seen_paths.add(result.path)
                line = f"- {result.path} [{result.tier}]: {result.snippet}"
                if used_chars + len(line) + 1 > char_budget:
                    break
                lines.append(line)
                used_chars += len(line) + 1
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
