#!/usr/bin/env python3
"""Install icontext MCP and UserPromptSubmit hook into Claude settings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install_mcp(claude_dir: Path, icontext_root: Path, repo: Path) -> None:
    path = claude_dir / ".mcp.json"
    data = _read_json(path)
    servers = data.setdefault("mcpServers", {})
    servers["icontext"] = {
        "command": "python3",
        "args": [str(icontext_root / "mcp" / "server.py"), "--repo", str(repo)],
    }
    _write_json(path, data)


def install_hook(claude_dir: Path, icontext_root: Path, repo: Path) -> None:
    path = claude_dir / "settings.json"
    data = _read_json(path)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("UserPromptSubmit", [])
    command = (
        f"ICONTEXT_ROOT={icontext_root} ICONTEXT_VAULT={repo} "
        f"{icontext_root / 'hooks' / 'user-prompt-submit'}"
    )
    desired = {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
                "statusMessage": "Searching context vault",
            }
        ],
    }
    entries[:] = [
        entry
        for entry in entries
        if not any("user-prompt-submit" in hook.get("command", "") for hook in entry.get("hooks", []))
    ]
    entries.append(desired)
    _write_json(path, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude-dir", default="~/.claude")
    parser.add_argument("--icontext-root", default="~/icontext")
    parser.add_argument("--repo", default="~/context")
    args = parser.parse_args()

    claude_dir = Path(args.claude_dir).expanduser().resolve()
    icontext_root = Path(args.icontext_root).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()
    install_mcp(claude_dir, icontext_root, repo)
    install_hook(claude_dir, icontext_root, repo)
    print(f"icontext: installed Claude MCP and UserPromptSubmit hook for {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
