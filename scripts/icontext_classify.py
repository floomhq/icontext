#!/usr/bin/env python3
"""Rule-based sensitivity classifier for fbrain.

The classifier is intentionally deterministic. It is the local safety net used
by hooks and CI; LLM review can be layered on top later without making pushes
depend on a paid or unavailable provider.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TIERS = {
    "shareable": 0,
    "internal": 1,
    "vault": 2,
}


VAULT_PATH_PATTERNS = (
    "secret",
    "credential",
    "password",
    "private_key",
    "ssh",
    ".env",
    "token",
    "apikey",
    "api-key",
    "passport",
    "driver-license",
    "bank",
    "tax",
    "taxes/",
    "legal/incidents/",
    "whatsapp",
)

VAULT_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]", re.I),
    re.compile(r"\b(?:ssn|social security number)\b", re.I),
    re.compile(r"\b(?:iban|swift|routing number|account number)\b", re.I),
    re.compile(r"\b(?:passport|driver'?s license|tax id)\b", re.I),
)

INTERNAL_PATH_PATTERNS = (
    "strategy/",
    "partnerships/",
    "team/",
    "pitches/",
    "projects/",
    "infra/",
    "applications/",
    "research/",
    "documents/",
)

INTERNAL_CONTENT_PATTERNS = (
    re.compile(r"\b(?:confidential|internal only|do not share|nda)\b", re.I),
    re.compile(r"\b(?:runway|burn rate|cap table|investor|fundraising)\b", re.I),
    re.compile(r"\b(?:customer|client|partner|contract|invoice)\b", re.I),
)


@dataclass(frozen=True)
class Classification:
    path: str
    tier: str
    rank: int
    reasons: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "path": self.path,
                "tier": self.tier,
                "rank": self.rank,
                "reasons": list(self.reasons),
            },
            sort_keys=True,
        )


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return ""

    if b"\0" in data[:4096]:
        return ""

    return data[:200_000].decode("utf-8", errors="ignore")


def classify(path: str, repo_root: Path | None = None) -> Classification:
    repo_root = repo_root or Path.cwd()
    rel_path = path.replace("\\", "/")
    lower_path = rel_path.lower()
    text = _read_text(repo_root / rel_path)
    reasons: list[str] = []

    for pattern in VAULT_PATH_PATTERNS:
        if pattern in lower_path:
            reasons.append(f"path:{pattern}")
            return Classification(rel_path, "vault", TIERS["vault"], tuple(reasons))

    for regex in VAULT_CONTENT_PATTERNS:
        if regex.search(text):
            reasons.append(f"content:{regex.pattern}")
            return Classification(rel_path, "vault", TIERS["vault"], tuple(reasons))

    for pattern in INTERNAL_PATH_PATTERNS:
        if pattern in lower_path:
            reasons.append(f"path:{pattern}")
            return Classification(rel_path, "internal", TIERS["internal"], tuple(reasons))

    for regex in INTERNAL_CONTENT_PATTERNS:
        if regex.search(text):
            reasons.append(f"content:{regex.pattern}")
            return Classification(rel_path, "internal", TIERS["internal"], tuple(reasons))

    reasons.append("default:shareable")
    return Classification(rel_path, "shareable", TIERS["shareable"], tuple(reasons))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: icontext_classify.py PATH [PATH...]", file=sys.stderr)
        return 2

    for item in argv[1:]:
        print(classify(item).to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

