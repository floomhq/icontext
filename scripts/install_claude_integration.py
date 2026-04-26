#!/usr/bin/env python3
"""Install icontext MCP and prompt integrations into local coding agents."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _server_script(icontext_root: Path) -> str:
    return str(icontext_root / "mcp" / "server.py")


def _json_string(value: str) -> str:
    return json.dumps(value)


def install_claude_mcp(claude_dir: Path, icontext_root: Path, repo: Path) -> None:
    path = claude_dir / ".mcp.json"
    data = _read_json(path)
    servers = data.setdefault("mcpServers", {})
    servers["icontext"] = {
        "command": "python3",
        "args": [_server_script(icontext_root), "--repo", str(repo)],
    }
    _write_json(path, data)


def install_claude_hook(claude_dir: Path, icontext_root: Path, repo: Path) -> None:
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


def install_claude(claude_dir: Path, icontext_root: Path, repo: Path) -> None:
    install_claude_mcp(claude_dir, icontext_root, repo)
    install_claude_hook(claude_dir, icontext_root, repo)


def install_cursor(cursor_mcp: Path, icontext_root: Path, repo: Path) -> None:
    data = _read_json(cursor_mcp)
    servers = data.setdefault("mcpServers", {})
    servers["icontext"] = {
        "command": "python3",
        "args": [_server_script(icontext_root), "--repo", str(repo)],
        "env": {},
    }
    _write_json(cursor_mcp, data)


def install_opencode(opencode_config: Path, icontext_root: Path, repo: Path) -> None:
    data = _read_json(opencode_config)
    servers = data.setdefault("mcp", {})
    servers["icontext"] = {
        "type": "local",
        "command": ["python3", _server_script(icontext_root), "--repo", str(repo)],
        "enabled": True,
    }
    _write_json(opencode_config, data)


def _codex_block(icontext_root: Path, repo: Path) -> str:
    args = ", ".join(_json_string(arg) for arg in [_server_script(icontext_root), "--repo", str(repo)])
    return "\n".join(
        [
            "[mcp_servers.icontext]",
            'command = "python3"',
            f"args = [{args}]",
            "",
        ]
    )


def install_codex(codex_config: Path, icontext_root: Path, repo: Path) -> None:
    codex_config.parent.mkdir(parents=True, exist_ok=True)
    text = codex_config.read_text(encoding="utf-8") if codex_config.exists() else ""
    block = _codex_block(icontext_root, repo)
    pattern = re.compile(r"(?ms)^\[mcp_servers\.icontext\]\n.*?(?=^\[|\Z)")
    if pattern.search(text):
        text = pattern.sub(block, text)
    else:
        text = text.rstrip() + "\n\n" + block
    parsed = tomllib.loads(text)
    if parsed["mcp_servers"]["icontext"]["args"][-1] != str(repo):
        raise ValueError("Codex icontext MCP config did not round-trip")
    codex_config.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude-dir", default="~/.claude")
    parser.add_argument("--codex-config", default="~/.codex/config.toml")
    parser.add_argument("--cursor-mcp", default="~/.cursor/mcp.json")
    parser.add_argument("--opencode-config", default="~/.config/opencode/opencode.json")
    parser.add_argument("--icontext-root", default="~/icontext")
    parser.add_argument("--repo", default="~/context")
    parser.add_argument(
        "--agents",
        nargs="+",
        choices=["all", "claude", "codex", "cursor", "opencode"],
        default=["all"],
    )
    args = parser.parse_args()

    claude_dir = Path(args.claude_dir).expanduser().resolve()
    codex_config = Path(args.codex_config).expanduser()
    cursor_mcp = Path(args.cursor_mcp).expanduser()
    opencode_config = Path(args.opencode_config).expanduser()
    icontext_root = Path(args.icontext_root).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()
    requested = set(args.agents)
    if "all" in requested:
        requested = {"claude", "codex", "cursor", "opencode"}

    if "claude" in requested:
        install_claude(claude_dir, icontext_root, repo)
    if "codex" in requested:
        install_codex(codex_config, icontext_root, repo)
    if "cursor" in requested:
        install_cursor(cursor_mcp, icontext_root, repo)
    if "opencode" in requested:
        install_opencode(opencode_config, icontext_root, repo)

    print(f"icontext: installed {', '.join(sorted(requested))} integrations for {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
