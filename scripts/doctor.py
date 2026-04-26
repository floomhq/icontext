#!/usr/bin/env python3
"""Verify an icontext install end to end."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    status: str
    detail: str


class Doctor:
    def __init__(self, repo: Path, icontext_root: Path, query: str, deep: bool):
        self.repo = repo.expanduser().resolve()
        self.icontext_root = icontext_root.expanduser().resolve()
        self.query = query
        self.deep = deep
        self.checks: list[Check] = []

    def pass_(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "pass", detail))

    def warn(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "warn", detail))

    def fail(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "fail", detail))

    def run(self) -> int:
        self.check_prereqs()
        self.check_repo()
        self.check_hooks()
        self.check_config_files()
        self.check_gitcrypt()
        self.check_index()
        self.check_mcp_stdio()
        self.check_agent_configs()
        self.check_native_clients()
        if self.deep:
            self.check_secret_scan()
            self.check_github_action()
        return 1 if any(check.status == "fail" for check in self.checks) else 0

    def command(self, args: list[str], cwd: Path | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=cwd or self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

    def check_prereqs(self) -> None:
        for command in ["git", "python3", "gitleaks", "git-crypt", "git-lfs"]:
            path = shutil.which(command)
            if path:
                self.pass_(f"command:{command}", path)
            else:
                self.fail(f"command:{command}", "not found on PATH")

    def check_repo(self) -> None:
        if not (self.repo / ".git").exists():
            self.fail("repo", f"{self.repo} is not a git repo")
            return
        result = self.command(["git", "status", "--short"])
        if result.returncode != 0:
            self.fail("repo:status", result.stdout.strip())
        elif result.stdout.strip():
            self.warn("repo:clean", "working tree has uncommitted changes")
        else:
            self.pass_("repo:clean", "working tree clean")

    def check_hooks(self) -> None:
        for hook in ["pre-commit", "pre-push", "post-commit"]:
            path = self.repo / ".git" / "hooks" / hook
            target = self.icontext_root / "hooks" / hook
            if not path.exists():
                self.fail(f"hook:{hook}", "missing")
                continue
            if not path.resolve() == target.resolve():
                self.fail(f"hook:{hook}", f"points to {path.resolve()}, expected {target}")
                continue
            if not path.stat().st_mode & 0o111:
                self.fail(f"hook:{hook}", "not executable")
                continue
            self.pass_(f"hook:{hook}", str(target))

    def check_config_files(self) -> None:
        for rel in [".gitleaks.toml", ".icontext-tiers.yml", ".github/workflows/icontext-sensitivity.yml"]:
            path = self.repo / rel
            if path.exists():
                self.pass_(f"repo-config:{rel}", "present")
            else:
                self.fail(f"repo-config:{rel}", "missing")

    def check_gitcrypt(self) -> None:
        attrs = self.command(["git", "check-attr", "filter", "--", "vault/secretary/.env"])
        if attrs.returncode == 0 and "git-crypt" in attrs.stdout:
            self.pass_("git-crypt:attribute", "vault/** uses git-crypt filter")
        else:
            self.fail("git-crypt:attribute", attrs.stdout.strip() or "missing git-crypt attribute")

        blob = subprocess.run(
            ["git", "cat-file", "-p", "HEAD:vault/secretary/.env"],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        if blob.returncode == 0 and blob.stdout.startswith(b"\x00GITCRYPT"):
            self.pass_("git-crypt:blob", "vault/secretary/.env is encrypted in HEAD")
        else:
            self.fail("git-crypt:blob", "expected GITCRYPT header in HEAD blob")

    def check_index(self) -> None:
        db = self.repo / ".git" / "icontext" / "index.sqlite"
        marker = self.repo / ".git" / "icontext" / "last-indexed"
        if not db.exists():
            self.fail("index:sqlite", "missing")
            return
        count = marker.read_text(encoding="utf-8").strip() if marker.exists() else "unknown"
        self.pass_("index:sqlite", f"{db} ({count} indexed text files)")

    def check_mcp_stdio(self) -> None:
        server = self.icontext_root / "mcp" / "server.py"
        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "icontext-doctor", "version": "1"},
                        },
                    }
                ),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "search_vault",
                            "arguments": {"query": self.query, "limit": 1},
                        },
                    }
                ),
                "",
            ]
        )
        result = subprocess.run(
            [sys.executable, str(server), "--repo", str(self.repo)],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        if result.returncode != 0:
            self.fail("mcp:stdio", result.stdout.strip())
            return
        responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if len(responses) < 2 or "result" not in responses[-1]:
            self.fail("mcp:stdio", result.stdout.strip())
            return
        text = responses[-1]["result"]["content"][0]["text"]
        if text == "[]":
            self.fail("mcp:search", f"no results for {self.query!r}")
        else:
            self.pass_("mcp:search", f"{len(text)} response chars for {self.query!r}")

    def check_agent_configs(self) -> None:
        expected_args = [str(self.icontext_root / "mcp" / "server.py"), "--repo", str(self.repo)]
        self._check_json_server(
            "claude:mcp",
            Path("~/.claude/.mcp.json").expanduser(),
            ["mcpServers", "icontext"],
            expected_args,
        )
        settings = Path("~/.claude/settings.json").expanduser()
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            entries = data.get("hooks", {}).get("UserPromptSubmit", [])
            command = str(self.icontext_root / "hooks" / "user-prompt-submit")
            if any(command in hook.get("command", "") for entry in entries for hook in entry.get("hooks", [])):
                self.pass_("claude:prompt-hook", command)
            else:
                self.fail("claude:prompt-hook", "UserPromptSubmit hook missing")
        except Exception as exc:
            self.fail("claude:prompt-hook", str(exc))

        self._check_codex(expected_args)
        self._check_json_server(
            "cursor:mcp",
            Path("~/.cursor/mcp.json").expanduser(),
            ["mcpServers", "icontext"],
            expected_args,
        )
        self._check_json_server(
            "opencode:mcp",
            Path("~/.config/opencode/opencode.json").expanduser(),
            ["mcp", "icontext"],
            expected_args,
            command_key="command",
            command_in_args=True,
        )

    def _check_json_server(
        self,
        name: str,
        path: Path,
        keys: list[str],
        expected_args: list[str],
        command_key: str = "args",
        command_in_args: bool = False,
    ) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            node = data
            for key in keys:
                node = node[key]
            actual = node[command_key]
            if command_in_args:
                actual = actual[1:]
            if actual == expected_args:
                self.pass_(name, str(path))
            else:
                self.fail(name, f"unexpected args: {actual}")
        except Exception as exc:
            self.fail(name, str(exc))

    def _check_codex(self, expected_args: list[str]) -> None:
        path = Path("~/.codex/config.toml").expanduser()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            server = data["mcp_servers"]["icontext"]
            if server.get("command") == "python3" and server.get("args") == expected_args:
                self.pass_("codex:mcp", str(path))
            else:
                self.fail("codex:mcp", f"unexpected config: {server}")
        except Exception as exc:
            self.fail("codex:mcp", str(exc))

    def check_native_clients(self) -> None:
        codex = self.command(["codex", "mcp", "get", "icontext"], cwd=Path.home(), timeout=15)
        if codex.returncode == 0 and str(self.repo) in codex.stdout:
            self.pass_("codex:native", "codex mcp get icontext")
        else:
            self.fail("codex:native", codex.stdout.strip())

        opencode = self.command(["opencode", "mcp", "list"], cwd=Path.home(), timeout=45)
        if opencode.returncode == 0 and "icontext" in opencode.stdout and "connected" in opencode.stdout:
            self.pass_("opencode:native", "opencode reports icontext connected")
        else:
            self.fail("opencode:native", opencode.stdout.strip())

        if shutil.which("cursor-agent"):
            cursor = self.command(["cursor-agent", "mcp", "list-tools", "icontext"], cwd=Path.home(), timeout=45)
            if cursor.returncode == 0 and "search_vault" in cursor.stdout:
                self.pass_("cursor:native", "cursor-agent lists icontext tools")
            else:
                self.fail("cursor:native", cursor.stdout.strip())
        elif shutil.which("cursor"):
            self.warn("cursor:native", "cursor CLI present, but cursor-agent health command is unavailable")
        else:
            self.warn("cursor:native", "cursor-agent not present; config and MCP server validated directly")

    def check_secret_scan(self) -> None:
        result = self.command(["gitleaks", "dir", ".", "--config", ".gitleaks.toml", "--redact", "--no-banner"], timeout=60)
        if result.returncode == 0:
            self.pass_("gitleaks:dir", "no leaks found")
        else:
            self.fail("gitleaks:dir", result.stdout.strip())

    def check_github_action(self) -> None:
        if not shutil.which("gh"):
            self.warn("github:action", "gh not installed")
            return
        result = self.command(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "icontext sensitivity",
                "--limit",
                "1",
                "--json",
                "status,conclusion,headSha,workflowName",
            ],
            timeout=20,
        )
        if result.returncode != 0:
            self.warn("github:action", result.stdout.strip())
            return
        runs = json.loads(result.stdout or "[]")
        if runs and runs[0].get("status") == "completed" and runs[0].get("conclusion") == "success":
            self.pass_("github:action", runs[0].get("headSha", "success"))
        else:
            self.fail("github:action", result.stdout.strip() or "no workflow run found")


def print_text(checks: list[Check]) -> None:
    symbols = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for check in checks:
        print(f"{symbols[check.status]} {check.name}: {check.detail}")
    totals = {status: sum(1 for check in checks if check.status == status) for status in ["pass", "warn", "fail"]}
    print(f"summary: {totals['pass']} pass, {totals['warn']} warn, {totals['fail']} fail")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="~/context")
    parser.add_argument("--icontext-root", default="~/icontext")
    parser.add_argument("--query", default="OpenPaper citations academic")
    parser.add_argument("--deep", action="store_true", help="run slower gitleaks and GitHub checks")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args()

    doctor = Doctor(Path(args.repo), Path(args.icontext_root), args.query, args.deep)
    exit_code = doctor.run()
    if args.json:
        print(json.dumps([check.__dict__ for check in doctor.checks], indent=2))
    else:
        print_text(doctor.checks)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
