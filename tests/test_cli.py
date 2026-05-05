"""CLI tests using subprocess + a temp vault."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = str(Path(__file__).resolve().parents[1] / "cli.py")


def _safe_env(home: str | None = None) -> dict:
    """Return an environment with HOME overridden to a temp dir.

    Init writes to ~/.claude/CLAUDE.md and ~/.claude/skills/. Tests must not
    pollute the real user home.
    """
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = home
        env.pop("FBRAIN_VAULT", None)
        env.pop("ICONTEXT_VAULT", None)
    return env


def run(*args: str, vault: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run fbrain CLI.

    For subcommands (init, status, sync, share, doctor): `args[0]` is the subcommand
    and `--vault` is injected right after it (each subparser registers --vault locally).
    For top-level flags (--help, --version): they are passed directly with no --vault.
    """
    _SUBCOMMANDS = {"init", "status", "connect", "sync", "search", "rebuild", "share", "doctor", "skills", "push", "pull", "autosync"}
    cmd = [sys.executable, CLI]
    if args and args[0] in _SUBCOMMANDS:
        cmd += [args[0]]
        if vault:
            cmd += ["--vault", vault]
        cmd += list(args[1:])
    else:
        cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------
# --help and --version
# ---------------------------------------------------------------------------

class TestHelpAndVersion(unittest.TestCase):

    def test_help_exits_0_and_lists_subcommands(self):
        result = run("--help")
        self.assertEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        for subcmd in ("init", "status", "connect", "sync", "share", "doctor"):
            self.assertIn(subcmd, output, f"subcommand '{subcmd}' missing from --help output")

    def test_version_exits_0_and_prints_version(self):
        result = run("--version")
        # argparse sends --version to stdout on some platforms, stderr on others
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0)
        self.assertRegex(output, r"fbrain \d+\.\d+\.\d+")

    def test_no_args_exits_1_and_prints_help(self):
        result = run()
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertIn("fbrain", output.lower())


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus(unittest.TestCase):

    def test_status_nonexistent_vault_exits_1_with_helpful_message(self):
        result = run("status", vault="/nonexistent/path/vault_abc123")
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        # Should mention the missing vault and how to fix it
        self.assertTrue(
            "not found" in output.lower() or "init" in output.lower(),
            f"Expected helpful message in output, got: {output!r}"
        )

    def test_status_with_existing_empty_vault_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = tmp
            result = run("status", vault=vault)
        self.assertEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("vault", output.lower())


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit(unittest.TestCase):

    def test_init_creates_expected_folder_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "my-vault"
            result = run("init", vault=str(vault), env=_safe_env(str(home)))
            output = result.stdout + result.stderr
            self.assertTrue(
                vault.exists(),
                f"Vault directory not created. CLI output: {output!r}"
            )
            for subdir in ("shareable", "internal"):
                self.assertTrue(
                    (vault / subdir).exists(),
                    f"Missing subdir '{subdir}'. CLI output: {output!r}"
                )

    def test_init_creates_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "git-vault"
            run("init", vault=str(vault), env=_safe_env(str(home)))
            self.assertTrue(
                (vault / ".git").exists(),
                "Expected .git directory after fbrain init"
            )

    def test_init_installs_skill_files(self):
        """Skills should land in ~/.claude/skills/ after init."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "skill-vault"
            result = run("init", vault=str(vault), env=_safe_env(str(home)))
            output = result.stdout + result.stderr
            skills_dir = home / ".claude" / "skills"
            for name in ("fbrain-populate-profile", "fbrain-refresh-profile", "fbrain-share-card"):
                skill = skills_dir / name / "SKILL.md"
                self.assertTrue(
                    skill.exists(),
                    f"Missing skill {skill}. CLI output: {output!r}"
                )
                content = skill.read_text()
                self.assertIn("---", content, "skill missing frontmatter")
                self.assertIn("name:", content, "skill missing name")

    def test_init_installs_cursor_rules(self):
        """Cursor .mdc rules should land in ~/.cursor/rules/."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "cursor-vault"
            run("init", vault=str(vault), env=_safe_env(str(home)))
            rules_dir = home / ".cursor" / "rules"
            for name in ("fbrain-populate-profile", "fbrain-refresh-profile", "fbrain-share-card"):
                self.assertTrue((rules_dir / f"{name}.mdc").exists(),
                                f"Missing cursor rule {name}.mdc")

    def test_init_writes_claude_md_snippet_referencing_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "claude-vault"
            run("init", vault=str(vault), env=_safe_env(str(home)))
            claude_md = home / ".claude" / "CLAUDE.md"
            self.assertTrue(claude_md.exists(), "CLAUDE.md not created")
            text = claude_md.read_text()
            self.assertIn("<!-- fbrain -->", text)
            self.assertIn("fbrain-populate-profile", text)
            self.assertIn("fbrain-refresh-profile", text)
            self.assertIn("fbrain-share-card", text)
            self.assertIn("internal/profile/user.md", text)

    def test_init_does_not_require_gemini_key(self):
        """Init must succeed with no GEMINI_API_KEY in env."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "no-key-vault"
            env = _safe_env(str(home))
            env.pop("GEMINI_API_KEY", None)
            env.pop("GEMINI_API_KEY_PAID", None)
            result = run("init", vault=str(vault), env=env)
            self.assertEqual(result.returncode, 0,
                             f"init failed without GEMINI_API_KEY. Output: {result.stdout + result.stderr!r}")
            output = result.stdout + result.stderr
            # No blocking warnings about Gemini key
            for bad in ("missing GEMINI_API_KEY", "GEMINI_API_KEY not set", "required for"):
                self.assertNotIn(bad, output,
                                 f"init should not block on Gemini key: found {bad!r}")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

class TestSync(unittest.TestCase):

    def test_sync_empty_vault_exits_1_with_next_step_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "empty-vault"
            vault.mkdir()
            result = run("sync", vault=str(vault))
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        # Should mention connecting a source or similar next-step hint
        self.assertTrue(
            "connect" in output.lower() or "configured" in output.lower() or "source" in output.lower(),
            f"Expected next-step guidance in output, got: {output!r}"
        )


# ---------------------------------------------------------------------------
# share
# ---------------------------------------------------------------------------

class TestShare(unittest.TestCase):

    def test_share_empty_vault_exits_1_with_helpful_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "share-vault"
            vault.mkdir()
            result = run("share", vault=str(vault))
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        # Should mention syncing or connecting
        self.assertTrue(
            "sync" in output.lower() or "connect" in output.lower() or "card" in output.lower(),
            f"Expected helpful guidance in output, got: {output!r}"
        )


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------

class TestSkills(unittest.TestCase):

    def test_skills_list_after_init_shows_three_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            run("init", vault=str(vault), env=_safe_env(str(home)))
            result = run("skills", "list", env=_safe_env(str(home)))
            self.assertEqual(result.returncode, 0)
            output = result.stdout + result.stderr
            for name in ("fbrain-populate-profile", "fbrain-refresh-profile", "fbrain-share-card"):
                self.assertIn(name, output)

    def test_skills_no_action_defaults_to_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            run("init", vault=str(vault), env=_safe_env(str(home)))
            result = run("skills", env=_safe_env(str(home)))
            self.assertEqual(result.returncode, 0)
            output = result.stdout + result.stderr
            self.assertIn("fbrain-populate-profile", output)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

class TestDoctor(unittest.TestCase):

    def test_doctor_with_temp_dir_runs_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "doctor-vault"
            vault.mkdir()
            result = run("doctor", vault=str(vault))
        # Doctor may report failures but must not crash (returncode != crash signal)
        # returncode 0 (all pass) or 1 (some fail) are both valid; anything else is a bug
        self.assertIn(
            result.returncode, (0, 1),
            f"Doctor crashed with returncode {result.returncode}.\nStdout: {result.stdout}\nStderr: {result.stderr}"
        )

    def test_doctor_output_contains_summary_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "doctor-vault2"
            vault.mkdir()
            result = run("doctor", vault=str(vault))
        output = result.stdout + result.stderr
        # Doctor should always end with a summary line
        self.assertIn(
            "pass", output.lower(),
            f"Expected 'pass' in doctor summary. Output: {output!r}"
        )


# ---------------------------------------------------------------------------
# push / pull / autosync (multi-device sync)
# ---------------------------------------------------------------------------

def _make_git_vault(path: Path) -> None:
    """Create a minimal git repo at path with one initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@local"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    (path / "README.md").write_text("test vault\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


class TestPush(unittest.TestCase):

    def test_push_help_exits_0(self):
        result = run("push", "--help")
        self.assertEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("push", output.lower())

    def test_push_nonexistent_vault_exits_1(self):
        result = run("push", vault="/nonexistent/path/push_xyz")
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertTrue(
            "not found" in output.lower() or "init" in output.lower(),
            f"Expected helpful message, got: {output!r}"
        )

    def test_push_no_origin_exits_1_with_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "no-origin-vault"
            _make_git_vault(vault)
            result = run("push", vault=str(vault))
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertTrue(
            "origin" in output.lower() and ("gh repo create" in output.lower() or "remote" in output.lower()),
            f"Expected gh repo create hint, got: {output!r}"
        )


class TestPull(unittest.TestCase):

    def test_pull_help_exits_0(self):
        result = run("pull", "--help")
        self.assertEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("pull", output.lower())

    def test_pull_no_origin_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "no-origin-pull-vault"
            _make_git_vault(vault)
            result = run("pull", vault=str(vault))
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertTrue(
            "origin" in output.lower(),
            f"Expected origin hint, got: {output!r}"
        )

    def test_pull_non_git_vault_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "plain-vault"
            vault.mkdir()
            result = run("pull", vault=str(vault))
        self.assertEqual(result.returncode, 1)


class TestAutosync(unittest.TestCase):

    def test_autosync_help_exits_0(self):
        result = run("autosync", "--help")
        self.assertEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("autosync", output.lower())
        # all three actions referenced
        for action in ("start", "stop", "status"):
            self.assertIn(action, output.lower())

    def test_autosync_no_action_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            result = run("autosync", vault=str(vault))
        self.assertEqual(result.returncode, 1)

    def test_autosync_status_in_clean_home_reports_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            vault.mkdir()
            result = run("autosync", "status", vault=str(vault), env=_safe_env(str(home)))
            output = result.stdout + result.stderr
            # Status should exit 0 (informational), and report not running OR not active
            self.assertEqual(result.returncode, 0,
                             f"autosync status crashed: {output!r}")
            self.assertTrue(
                "not running" in output.lower() or "not installed" in output.lower() or "no timer" in output.lower() or "no plist" in output.lower(),
                f"Expected 'not running' state, got: {output!r}"
            )


if __name__ == "__main__":
    unittest.main()
