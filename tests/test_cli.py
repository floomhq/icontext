"""CLI tests using subprocess + a temp vault."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = str(Path(__file__).resolve().parents[1] / "cli.py")


def run(*args: str, vault: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run icontext CLI.

    For subcommands (init, status, sync, share, doctor): `args[0]` is the subcommand
    and `--vault` is injected right after it (each subparser registers --vault locally).
    For top-level flags (--help, --version): they are passed directly with no --vault.
    """
    _SUBCOMMANDS = {"init", "status", "connect", "sync", "search", "rebuild", "share", "doctor"}
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
        self.assertIn("0.2.0", output)

    def test_no_args_exits_1_and_prints_help(self):
        result = run()
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertIn("icontext", output.lower())


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
            vault = Path(tmp) / "my-vault"
            result = run("init", vault=str(vault))
            # init may fail if external tools are unavailable; check what was created
            # At minimum, the directory and subdirs should exist
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
            vault = Path(tmp) / "git-vault"
            run("init", vault=str(vault))
            self.assertTrue(
                (vault / ".git").exists(),
                "Expected .git directory after icontext init"
            )


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


if __name__ == "__main__":
    unittest.main()
