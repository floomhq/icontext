#!/usr/bin/env python3
"""Verify an icontext install end to end."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
        # Detect install mode. Skills-first (default for v0.2+) skips legacy
        # standard-mode checks (git hooks in vault, .gitleaks.toml in vault,
        # MCP server registered with vault path, etc.) since those only apply
        # when install.sh was run with --mode standard.
        self.skills_first = self._detect_skills_first()

    def _detect_skills_first(self) -> bool:
        """Skills-first mode is the default for `icontext init`. Signal: at
        least one icontext skill installed in ~/.claude/skills/, AND no legacy
        marker present in the vault."""
        skills_dir = Path("~/.claude/skills").expanduser()
        has_skills = skills_dir.is_dir() and any(
            (skills_dir / f"icontext-{name}/SKILL.md").is_file()
            for name in ("populate-profile", "refresh-profile", "share-card")
        )
        legacy_marker = self.repo / ".icontext" / "manifest.json"
        return has_skills and not legacy_marker.exists()

    def _legacy_check(self, name: str, status: str, detail: str) -> None:
        """In skills-first mode, downgrade failures of legacy-only checks
        to warns with a note so users aren't alarmed by missing vault hooks."""
        if self.skills_first and status == "fail":
            self.warn(name, f"{detail} (legacy-mode only — not required for skills-first install)")
        elif status == "fail":
            self.fail(name, detail)
        elif status == "warn":
            self.warn(name, detail)
        else:
            self.pass_(name, detail)

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
        self.check_vault_blobs()
        self.check_index()
        self.check_mcp_stdio()
        self.check_agent_configs()
        self.check_native_clients()
        self.check_connectors()
        self.check_sources()
        self.check_profile()
        self.check_environment()
        self.check_claude_integration()
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
        # Required for any mode
        for command in ["git", "python3"]:
            path = shutil.which(command)
            if path:
                self.pass_(f"command:{command}", path)
            else:
                self.fail(f"command:{command}", "not found on PATH")
        # Optional: only required for legacy standard-mode install
        for command in ["gitleaks", "git-crypt", "git-lfs"]:
            path = shutil.which(command)
            if path:
                self.pass_(f"command:{command}", path)
            else:
                self._legacy_check(f"command:{command}", "fail", "not found on PATH")

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
                self._legacy_check(f"hook:{hook}", "fail", "missing")
                continue
            if not path.resolve() == target.resolve():
                self._legacy_check(f"hook:{hook}", "fail", f"points to {path.resolve()}, expected {target}")
                continue
            if not path.stat().st_mode & 0o111:
                self._legacy_check(f"hook:{hook}", "fail", "not executable")
                continue
            self.pass_(f"hook:{hook}", str(target))

    def check_config_files(self) -> None:
        for rel in [".gitleaks.toml", ".icontext-tiers.yml", ".github/workflows/icontext-sensitivity.yml"]:
            path = self.repo / rel
            if path.exists():
                self.pass_(f"repo-config:{rel}", "present")
            else:
                self._legacy_check(f"repo-config:{rel}", "fail", "missing")

    def check_gitcrypt(self) -> None:
        # Find the first tracked file in vault/ (if any) to test git-crypt attribute and encryption
        files_result = self.command(["git", "ls-files", "-z", "vault/"], timeout=15)
        vault_files = [f for f in files_result.stdout.split("\0") if f] if files_result.returncode == 0 else []

        if not vault_files:
            # No files in vault/ yet — skip encryption checks
            self.warn("git-crypt:attribute", "vault/ is empty — no files to check encryption on")
            return

        sample_file = vault_files[0]

        attrs = self.command(["git", "check-attr", "filter", "--", sample_file])
        if attrs.returncode == 0 and "git-crypt" in attrs.stdout:
            self.pass_("git-crypt:attribute", f"vault/** uses git-crypt filter (checked {sample_file})")
        else:
            self.fail("git-crypt:attribute", attrs.stdout.strip() or f"missing git-crypt attribute on {sample_file}")

        blob = subprocess.run(
            ["git", "cat-file", "-p", f"HEAD:{sample_file}"],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        if blob.returncode == 0 and blob.stdout.startswith(b"\x00GITCRYPT"):
            self.pass_("git-crypt:blob", f"{sample_file} is encrypted in HEAD")
        else:
            self.fail("git-crypt:blob", f"expected GITCRYPT header in HEAD blob for {sample_file}")

    def check_vault_blobs(self) -> None:
        files = self.command(["git", "ls-files", "-z", "vault/"], timeout=30)
        if files.returncode != 0:
            self.fail("git-crypt:vault-blobs", files.stdout.strip())
            return
        paths = [item for item in files.stdout.split("\0") if item]
        failures: list[str] = []
        for rel_path in paths:
            attrs = self.command(["git", "check-attr", "filter", "--", rel_path], timeout=15)
            if "git-crypt" not in attrs.stdout:
                failures.append(f"{rel_path}: missing git-crypt filter")
                continue
            blob = subprocess.run(
                ["git", "cat-file", "-p", f"HEAD:{rel_path}"],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
            )
            if blob.returncode != 0 or not blob.stdout.startswith(b"\x00GITCRYPT"):
                failures.append(f"{rel_path}: HEAD blob is not git-crypt encrypted")
                if len(failures) >= 10:
                    break
        if failures:
            self.fail("git-crypt:vault-blobs", "; ".join(failures))
        else:
            self.pass_("git-crypt:vault-blobs", f"{len(paths)} tracked vault file(s) encrypted in HEAD")

    def check_index(self) -> None:
        db = self.repo / ".git" / "icontext" / "index.sqlite"
        marker = self.repo / ".git" / "icontext" / "last-indexed"
        if not db.exists():
            self._legacy_check("index:sqlite", "fail", "missing — run: icontext rebuild")
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
        try:
            responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            self.fail("mcp:stdio", f"invalid JSON in server output: {exc}")
            return
        if len(responses) < 2 or "result" not in responses[-1]:
            self.fail("mcp:stdio", result.stdout.strip())
            return
        text = responses[-1]["result"]["content"][0]["text"]
        if text == "[]":
            self._legacy_check("mcp:search", "fail", f"no results for {self.query!r} — run: icontext rebuild")
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
            elif self.skills_first and "icontext" in str(actual):
                # Skills-first: each `icontext init` registers MCP for that vault.
                # If icontext is registered at all, the user is wired up.
                self.pass_(name, f"{path} (registered for a different vault)")
            else:
                self._legacy_check(name, "fail", f"unexpected args: {actual}")
        except Exception as exc:
            self._legacy_check(name, "fail", str(exc))

    def _check_codex(self, expected_args: list[str]) -> None:
        path = Path("~/.codex/config.toml").expanduser()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            server = data["mcp_servers"]["icontext"]
            if server.get("command") == "python3" and server.get("args") == expected_args:
                self.pass_("codex:mcp", str(path))
            elif self.skills_first and server.get("command") == "python3":
                self.pass_("codex:mcp", f"{path} (registered for a different vault)")
            else:
                self._legacy_check("codex:mcp", "fail", f"unexpected config: {server}")
        except Exception as exc:
            self._legacy_check("codex:mcp", "fail", str(exc))

    def check_native_clients(self) -> None:
        codex = self.command(["codex", "mcp", "get", "icontext"], cwd=Path.home(), timeout=15)
        if codex.returncode == 0 and str(self.repo) in codex.stdout:
            self.pass_("codex:native", "codex mcp get icontext")
        elif self.skills_first and codex.returncode == 0 and "icontext" in codex.stdout:
            self.pass_("codex:native", "codex has icontext registered (for a different vault)")
        else:
            self._legacy_check("codex:native", "fail", codex.stdout.strip())

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

    # ------------------------------------------------------------------
    # New install-state checks (connector layer, sources, profile, env,
    # Claude Code integration)
    # ------------------------------------------------------------------

    def check_connectors(self) -> None:
        """Check that connector files are present in the iContext install root.

        In the skills-first architecture, connectors live in ~/icontext/connectors/
        (the install root), not inside the vault. The vault gets skills + folder
        structure; sync (which uses connectors) is opt-in and runs from the install.
        """
        connectors_dir = self.icontext_root / "connectors"
        if connectors_dir.is_dir():
            self.pass_("connectors:dir", str(connectors_dir))
        else:
            self.fail("connectors:dir", f"{connectors_dir} missing")

        for filename in ("base.py", "gmail.py", "linkedin.py"):
            path = connectors_dir / filename
            if path.exists():
                self.pass_(f"connectors:{filename}", str(path))
            else:
                self.fail(f"connectors:{filename}", f"{path} missing")

        cli_path = self.icontext_root / "cli.py"
        if cli_path.exists():
            self.pass_("connectors:cli.py", str(cli_path))
        else:
            self.fail("connectors:cli.py", f"{cli_path} missing")

        symlink = Path("~/.local/bin/icontext").expanduser()
        if symlink.exists() or symlink.is_symlink():
            target = symlink.resolve() if symlink.is_symlink() else symlink
            self.pass_("connectors:symlink", f"{symlink} -> {target}")
        else:
            self.warn("connectors:symlink", f"{symlink} not found (run install.sh to create)")

    def check_sources(self) -> None:
        """Check connector config, last_sync timestamps, and profile file presence."""
        import importlib
        from datetime import UTC, datetime, timedelta

        cfg_path = self.repo / ".icontext" / "connectors.json"
        if not cfg_path.exists():
            self.warn("sources:config", "connectors.json not found — run: icontext connect gmail")
            return

        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.fail("sources:config", f"cannot parse connectors.json: {exc}")
            return

        self.pass_("sources:config", f"{len(cfg)} source(s) configured: {', '.join(cfg.keys())}")

        stale_threshold = datetime.now(UTC) - timedelta(days=14)
        for source_name, source_cfg in cfg.items():
            last_sync_str = source_cfg.get("last_sync")
            if not last_sync_str:
                self.warn(f"sources:{source_name}:last_sync", "never synced — run: icontext sync")
            else:
                try:
                    ts = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00"))
                    if ts < stale_threshold:
                        days = (datetime.now(UTC) - ts).days
                        self.warn(
                            f"sources:{source_name}:last_sync",
                            f"stale ({days}d ago) — run: icontext sync {source_name}",
                        )
                    else:
                        self.pass_(f"sources:{source_name}:last_sync", last_sync_str)
                except ValueError:
                    self.warn(f"sources:{source_name}:last_sync", f"unparseable timestamp: {last_sync_str!r}")

            profile_map = {
                "gmail": self.repo / "internal" / "profile" / "user.md",
                "linkedin": self.repo / "internal" / "profile" / "linkedin.md",
            }
            if source_name in profile_map:
                profile_path = profile_map[source_name]
                if profile_path.exists():
                    self.pass_(f"sources:{source_name}:profile", str(profile_path))
                else:
                    self.warn(
                        f"sources:{source_name}:profile",
                        f"{profile_path} missing — run: icontext sync {source_name}",
                    )

    def check_profile(self) -> None:
        """Check that profile and context card files exist."""
        cfg_path = self.repo / ".icontext" / "connectors.json"
        if not cfg_path.exists():
            return

        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return

        if "gmail" in cfg:
            user_md = self.repo / "internal" / "profile" / "user.md"
            if user_md.exists():
                self.pass_("profile:user.md", str(user_md))
            else:
                self.fail("profile:user.md", f"{user_md} missing — run: icontext sync gmail")

        if "linkedin" in cfg:
            linkedin_md = self.repo / "internal" / "profile" / "linkedin.md"
            if linkedin_md.exists():
                self.pass_("profile:linkedin.md", str(linkedin_md))
            else:
                self.fail("profile:linkedin.md", f"{linkedin_md} missing — run: icontext sync linkedin")

        if cfg:
            card_md = self.repo / "shareable" / "profile" / "context-card.md"
            if card_md.exists():
                self.pass_("profile:context-card.md", str(card_md))
            else:
                self.warn("profile:context-card.md", f"{card_md} missing — run: icontext sync")

    def check_environment(self) -> None:
        """Check optional headless-sync deps. Default install requires none of these."""
        import importlib

        # All checks here are warn-level: the default flow uses agent skills, not Gemini.
        # These deps only matter for the optional `icontext sync` headless fallback.
        gemini_key = os.environ.get("GEMINI_API_KEY")
        google_key = os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            self.pass_("env:GEMINI_API_KEY", "set (optional — headless sync available)")
        elif google_key:
            self.pass_("env:GOOGLE_API_KEY", "set (optional — headless sync available)")
        else:
            self.pass_(
                "env:api_key",
                "not set — default flow uses agent skills (no key required)",
            )

        try:
            importlib.import_module("google.generativeai")
            self.pass_("env:google-generativeai", "importable (optional — for headless sync)")
        except ImportError:
            self.pass_(
                "env:google-generativeai",
                "not installed — install only if you want headless sync: pip install 'icontext[sync]'",
            )

        try:
            importlib.import_module("keyring")
            self.pass_("env:keyring", "importable (optional — for headless sync)")
        except ImportError:
            self.pass_(
                "env:keyring",
                "not installed — install only if you want headless sync: pip install 'icontext[sync]'",
            )

        # Skill files installed?
        skills_dir = Path("~/.claude/skills").expanduser()
        skill_names = ("icontext-populate-profile", "icontext-refresh-profile", "icontext-share-card")
        missing = [n for n in skill_names if not (skills_dir / n / "SKILL.md").exists()]
        if not missing:
            self.pass_("skills:claude", f"all 3 skills installed at {skills_dir}")
        else:
            self.fail("skills:claude", f"missing skills: {', '.join(missing)} — run: icontext init")

    def check_claude_integration(self) -> None:
        """Check CLAUDE.md snippet and .mcp.json entry."""
        claude_md = Path("~/.claude/CLAUDE.md").expanduser()
        if not claude_md.exists():
            self.warn("claude:CLAUDE.md", f"{claude_md} not found — run: icontext init")
        elif "<!-- icontext -->" in claude_md.read_text(encoding="utf-8", errors="replace"):
            self.pass_("claude:CLAUDE.md", "icontext snippet present")
        else:
            self.fail("claude:CLAUDE.md", "<!-- icontext --> snippet missing — run: icontext init")

        mcp_json = Path("~/.claude/.mcp.json").expanduser()
        if not mcp_json.exists():
            self.warn("claude:mcp.json", f"{mcp_json} not found — run: icontext init")
        else:
            try:
                data = json.loads(mcp_json.read_text(encoding="utf-8"))
                servers = data.get("mcpServers", {})
                if "icontext" in servers:
                    self.pass_("claude:mcp.json", "icontext server entry present")
                else:
                    self.fail("claude:mcp.json", "icontext entry missing — run: icontext init")
            except Exception as exc:
                self.fail("claude:mcp.json", f"cannot parse {mcp_json}: {exc}")

    def check_secret_scan(self) -> None:
        config_arg = []
        if (self.repo / ".gitleaks.toml").is_file():
            config_arg = ["--config", ".gitleaks.toml"]
        result = self.command(
            ["gitleaks", "detect", "--source", ".", "--no-banner", "--redact", "--exit-code", "1", *config_arg],
            timeout=60,
        )
        if result.returncode == 0:
            self.pass_("gitleaks:scan", "no leaks found")
        elif result.returncode == 1:
            self.fail("gitleaks:scan", result.stdout.strip()[:500])
        else:
            self.warn("gitleaks:scan", f"gitleaks failed: {result.stderr.strip()[:200]}")

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


class FreshInstallDoctor:
    HOOKS = ["pre-commit", "pre-push", "post-commit"]
    SCRIPT_FILES = [
        "icontext_classify.py",
        "check_tiers.py",
        "indexlib.py",
        "update_index.py",
        "prompt_context.py",
        "install_claude_integration.py",
        "doctor.py",
        "eval_retrieval.py",
    ]
    MANIFEST_CANDIDATES = [
        ".icontext/manifest.json",
        ".icontext/install-manifest.json",
        ".icontext-installed.json",
    ]

    def __init__(self, icontext_root: Path):
        self.icontext_root = icontext_root.expanduser().resolve()
        self.checks: list[Check] = []

    def pass_(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "pass", detail))

    def fail(self, name: str, detail: str) -> None:
        self.checks.append(Check(name, "fail", detail))

    def run(self) -> int:
        self.check_inputs()
        if any(check.status == "fail" for check in self.checks):
            return 1
        with tempfile.TemporaryDirectory(prefix="icontext-doctor-") as tempdir:
            temp_root = Path(tempdir)
            dry_repo = temp_root / "dry-run-repo"
            real_repo = temp_root / "real-repo"
            agent_repo = temp_root / "agent-repo"
            agent_home = temp_root / "agent-home"
            dry_ready = self.init_git_repo(dry_repo)
            real_ready = self.init_git_repo(real_repo)
            agent_ready = self.init_git_repo(agent_repo)
            if dry_ready:
                self.check_dry_run(dry_repo)
            if real_ready:
                self.check_real_install(real_repo)
            if agent_ready:
                self.check_agent_install(agent_repo, agent_home)
        return 1 if any(check.status == "fail" for check in self.checks) else 0

    def command(
        self,
        args: list[str],
        cwd: Path,
        timeout: int = 30,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        env = {**os.environ, "ICONTEXT_ROOT": str(self.icontext_root), "VAULT": str(cwd)}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

    def check_inputs(self) -> None:
        install = self.icontext_root / "install.sh"
        uninstall = self.icontext_root / "uninstall.sh"
        if not install.exists():
            self.fail("fresh-install:install-script", f"missing {install}")
        elif not install.is_file():
            self.fail("fresh-install:install-script", f"not a file: {install}")
        else:
            self.pass_("fresh-install:install-script", str(install))
        if not uninstall.exists():
            self.fail("fresh-install:uninstall-script", f"missing {uninstall}")
        elif not uninstall.is_file():
            self.fail("fresh-install:uninstall-script", f"not a file: {uninstall}")
        else:
            self.pass_("fresh-install:uninstall-script", str(uninstall))
        if shutil.which("git"):
            self.pass_("fresh-install:command:git", shutil.which("git") or "git")
        else:
            self.fail("fresh-install:command:git", "not found on PATH")

    def init_git_repo(self, repo: Path) -> bool:
        repo.mkdir(parents=True)
        result = subprocess.run(
            ["git", "init", "-q"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        if result.returncode == 0 and (repo / ".git").is_dir():
            self.pass_(f"fresh-install:init:{repo.name}", str(repo))
            return True
        else:
            self.fail(f"fresh-install:init:{repo.name}", result.stdout.strip())
            return False

    def check_dry_run(self, repo: Path) -> None:
        result = self.command(["bash", str(self.icontext_root / "install.sh"), "--dry-run", "--yes"], cwd=repo)
        if result.returncode == 0:
            self.pass_("fresh-install:dry-run", "install.sh --dry-run --yes exited 0")
        else:
            self.fail("fresh-install:dry-run", result.stdout.strip())
            return
        installed = [rel for rel in self.expected_installed_paths() if (repo / rel).exists()]
        installed.extend(f".git/hooks/{hook}" for hook in self.HOOKS if (repo / ".git" / "hooks" / hook).exists())
        if installed:
            self.fail("fresh-install:dry-run:no-mutations", f"created files: {', '.join(sorted(installed))}")
        else:
            self.pass_("fresh-install:dry-run:no-mutations", "no install artifacts created")

    def check_real_install(self, repo: Path) -> None:
        install = self.command(["bash", str(self.icontext_root / "install.sh"), "--yes"], cwd=repo)
        if install.returncode == 0:
            self.pass_("fresh-install:install", "install.sh --yes exited 0")
        else:
            self.fail("fresh-install:install", install.stdout.strip())
            return

        expected = self.expected_installed_paths()
        missing = [rel for rel in expected if not (repo / rel).exists()]
        missing.extend(f".git/hooks/{hook}" for hook in self.HOOKS if not (repo / ".git" / "hooks" / hook).exists())
        if missing:
            self.fail("fresh-install:files", f"missing: {', '.join(sorted(missing))}")
        else:
            self.pass_("fresh-install:files", f"{len(expected) + len(self.HOOKS)} expected files present")

        self.check_manifest(repo, expected)

        uninstall = self.command(["bash", str(self.icontext_root / "uninstall.sh"), "--yes"], cwd=repo)
        if uninstall.returncode == 0:
            self.pass_("fresh-install:uninstall", "uninstall.sh --yes exited 0")
        else:
            self.fail("fresh-install:uninstall", uninstall.stdout.strip())
            return

        remaining = [rel for rel in expected if (repo / rel).exists()]
        remaining.extend(f".git/hooks/{hook}" for hook in self.HOOKS if (repo / ".git" / "hooks" / hook).exists())
        if remaining:
            self.fail("fresh-install:uninstall:removed", f"remaining: {', '.join(sorted(remaining))}")
        else:
            self.pass_("fresh-install:uninstall:removed", "installed files removed")
        if (repo / ".git").is_dir():
            self.pass_("fresh-install:uninstall:repo", ".git directory remains")
        else:
            self.fail("fresh-install:uninstall:repo", ".git directory removed")

    def check_agent_install(self, repo: Path, home: Path) -> None:
        home.mkdir(parents=True)
        install = self.command(
            ["bash", str(self.icontext_root / "install.sh"), "--yes", "--mode", "agents"],
            cwd=repo,
            extra_env={"HOME": str(home)},
        )
        if install.returncode == 0:
            self.pass_("fresh-install:agents:install", "install.sh --yes --mode agents exited 0")
        else:
            self.fail("fresh-install:agents:install", install.stdout.strip())
            return

        expected = [
            home / ".claude" / ".mcp.json",
            home / ".claude" / "settings.json",
            home / ".codex" / "config.toml",
            home / ".cursor" / "mcp.json",
            home / ".config" / "opencode" / "opencode.json",
        ]
        missing = [str(path.relative_to(home)) for path in expected if not path.exists()]
        if missing:
            self.fail("fresh-install:agents:configs", f"missing: {', '.join(missing)}")
        else:
            self.pass_("fresh-install:agents:configs", "Claude, Codex, Cursor, and OpenCode configs written under temp HOME")

    def expected_installed_paths(self) -> list[str]:
        expected: list[str] = [".icontext-installed"]
        if (self.icontext_root / "config" / "gitleaks.toml").is_file():
            expected.append(".gitleaks.toml")
        if (self.icontext_root / "config" / "tiers.yml").is_file():
            expected.append(".icontext-tiers.yml")
        if (self.icontext_root / "workflows" / "sensitivity.yml").is_file():
            expected.append(".github/workflows/icontext-sensitivity.yml")
        if (self.icontext_root / "mcp" / "server.py").is_file():
            expected.append(".icontext/mcp/server.py")
        for script in self.SCRIPT_FILES:
            if (self.icontext_root / "scripts" / script).is_file():
                expected.append(f".icontext/scripts/{script}")
        return expected

    def check_manifest(self, repo: Path, expected: list[str]) -> None:
        manifest = next((repo / rel for rel in self.MANIFEST_CANDIDATES if (repo / rel).is_file()), None)
        if manifest is None:
            self.fail("fresh-install:manifest", "missing manifest JSON")
            return
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            self.fail("fresh-install:manifest", f"{manifest}: {exc}")
            return
        entries = self.manifest_entries(data, repo)
        if not entries:
            self.fail("fresh-install:manifest", f"{manifest}: no file entries")
            return
        absolute_fields = self.manifest_absolute_fields(data)
        if absolute_fields:
            self.fail(
                "fresh-install:manifest:privacy",
                f"absolute local paths recorded: {', '.join(absolute_fields)}",
            )
        else:
            self.pass_("fresh-install:manifest:privacy", "no absolute local paths recorded")
        expected_set = set(expected)
        manifest_paths = set(entries)
        missing = sorted(expected_set - manifest_paths)
        bad_hashes = [
            rel
            for rel in sorted(expected_set & manifest_paths)
            if entries[rel] != self.sha256(repo / rel)
        ]
        if missing or bad_hashes:
            detail = []
            if missing:
                detail.append(f"missing entries: {', '.join(missing)}")
            if bad_hashes:
                detail.append(f"bad sha256: {', '.join(bad_hashes)}")
            self.fail("fresh-install:manifest", "; ".join(detail))
        else:
            self.pass_("fresh-install:manifest", f"{manifest.relative_to(repo)} covers {len(expected_set)} files")

    def manifest_absolute_fields(self, data: object) -> list[str]:
        if not isinstance(data, dict):
            return []
        fields: list[str] = []
        for key in ["icontext_root", "vault"]:
            value = data.get(key)
            if isinstance(value, str) and Path(value).is_absolute():
                fields.append(key)
        files = data.get("files")
        if isinstance(files, list):
            for index, item in enumerate(files):
                if not isinstance(item, dict):
                    continue
                for key in ["path", "source", "link_target"]:
                    value = item.get(key)
                    if isinstance(value, str) and Path(value).is_absolute():
                        fields.append(f"files[{index}].{key}")
        return fields

    def manifest_entries(self, data: object, repo: Path) -> dict[str, str]:
        if isinstance(data, dict):
            files = data.get("files", data)
        else:
            files = data
        entries: dict[str, str] = {}
        if isinstance(files, dict):
            for path, value in files.items():
                if isinstance(value, str):
                    entries[str(path)] = value
                elif isinstance(value, dict) and isinstance(value.get("sha256"), str):
                    entries[str(path)] = value["sha256"]
        elif isinstance(files, list):
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
                    continue
                rel_path = item.get("relative_path")
                path = item.get("path")
                if isinstance(rel_path, str):
                    entries[rel_path] = item["sha256"]
                elif isinstance(path, str):
                    entries[self.repo_relative_manifest_path(path, repo)] = item["sha256"]
        return entries

    def repo_relative_manifest_path(self, path: str, repo: Path) -> str:
        manifest_path = Path(path)
        if manifest_path.is_absolute():
            try:
                return str(manifest_path.relative_to(repo))
            except ValueError:
                return path
        return path

    def sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


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
    parser.add_argument("--query", default="profile context")
    parser.add_argument("--deep", action="store_true", help="run slower gitleaks and GitHub checks")
    parser.add_argument("--fresh-install", action="store_true", help="verify install.sh and uninstall.sh in temp git repos")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args()

    if args.fresh_install:
        doctor = FreshInstallDoctor(Path(args.icontext_root))
    else:
        doctor = Doctor(Path(args.repo), Path(args.icontext_root), args.query, args.deep)
    exit_code = doctor.run()
    if args.json:
        print(json.dumps([check.__dict__ for check in doctor.checks], indent=2))
    else:
        print_text(doctor.checks)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
