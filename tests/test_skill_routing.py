"""Tests for the icontext-write-fact skill routing."""
from __future__ import annotations

import unittest
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
WRITE_FACT_SKILL = SKILLS_ROOT / "icontext-write-fact" / "SKILL.md"


class TestWriteFactSkillExists(unittest.TestCase):

    def test_skill_file_exists(self):
        self.assertTrue(
            WRITE_FACT_SKILL.exists(),
            f"icontext-write-fact SKILL.md missing at {WRITE_FACT_SKILL}"
        )

    def test_skill_has_frontmatter(self):
        content = WRITE_FACT_SKILL.read_text()
        self.assertTrue(
            content.startswith("---"),
            "SKILL.md must start with YAML frontmatter (---)"
        )
        self.assertIn("---", content[3:], "SKILL.md frontmatter must be closed with ---")

    def test_skill_frontmatter_has_name(self):
        content = WRITE_FACT_SKILL.read_text()
        self.assertIn("name: icontext-write-fact", content,
                      "frontmatter must declare name: icontext-write-fact")

    def test_skill_frontmatter_has_description(self):
        content = WRITE_FACT_SKILL.read_text()
        self.assertIn("description:", content,
                      "frontmatter must include a description field")

    def test_skill_frontmatter_has_triggers(self):
        content = WRITE_FACT_SKILL.read_text()
        self.assertIn("save to vault", content,
                      "skill description must include 'save to vault' trigger phrase")


class TestWriteFactDecisionTree(unittest.TestCase):
    """Verify the six routing categories are present in the decision tree."""

    def setUp(self):
        self.content = WRITE_FACT_SKILL.read_text()

    def test_legal_entity_category(self):
        self.assertIn("vault/legal/", self.content,
                      "decision tree must route legal/entity facts to vault/legal/")

    def test_project_category(self):
        self.assertIn("vault/projects/", self.content,
                      "decision tree must route project facts to vault/projects/")

    def test_team_category(self):
        self.assertIn("vault/team/", self.content,
                      "decision tree must route team/person facts to vault/team/")

    def test_strategy_category(self):
        self.assertIn("vault/strategy/", self.content,
                      "decision tree must route strategy facts to vault/strategy/")

    def test_secretary_logs_category(self):
        self.assertIn("vault/secretary/logs/", self.content,
                      "decision tree must route secretarial activity to vault/secretary/logs/")

    def test_credentials_category(self):
        self.assertIn("credentials", self.content,
                      "decision tree must address credentials/secrets routing")

    def test_antipattern_log_file_mentioned(self):
        # The specific bug that triggered this skill
        self.assertIn("vault/secretary/logs/icontext.md", self.content,
                      "skill must explicitly name the anti-pattern that caused the bug")


class TestWriteFactInstalledByInit(unittest.TestCase):
    """Verify the skill ships via icontext init."""

    def test_init_installs_write_fact_skill(self):
        import os
        import subprocess
        import sys
        import tempfile

        cli = str(Path(__file__).resolve().parents[1] / "cli.py")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("ICONTEXT_VAULT", None)
            subprocess.run(
                [sys.executable, cli, "init", "--vault", str(vault)],
                capture_output=True, text=True, env=env,
            )
            skill_path = home / ".claude" / "skills" / "icontext-write-fact" / "SKILL.md"
            self.assertTrue(
                skill_path.exists(),
                f"icontext-write-fact not installed by init. Expected at {skill_path}"
            )

    def test_init_installs_cursor_rule_for_write_fact(self):
        import os
        import subprocess
        import sys
        import tempfile

        cli = str(Path(__file__).resolve().parents[1] / "cli.py")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("ICONTEXT_VAULT", None)
            subprocess.run(
                [sys.executable, cli, "init", "--vault", str(vault)],
                capture_output=True, text=True, env=env,
            )
            cursor_path = home / ".cursor" / "rules" / "icontext-write-fact.mdc"
            self.assertTrue(
                cursor_path.exists(),
                f"icontext-write-fact cursor rule not installed. Expected at {cursor_path}"
            )

    def test_skills_list_shows_four_skills(self):
        import os
        import subprocess
        import sys
        import tempfile

        cli = str(Path(__file__).resolve().parents[1] / "cli.py")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("ICONTEXT_VAULT", None)
            subprocess.run(
                [sys.executable, cli, "init", "--vault", str(vault)],
                capture_output=True, text=True, env=env,
            )
            result = subprocess.run(
                [sys.executable, cli, "skills", "list"],
                capture_output=True, text=True, env=env,
            )
            output = result.stdout + result.stderr
            for name in (
                "icontext-populate-profile",
                "icontext-refresh-profile",
                "icontext-share-card",
                "icontext-write-fact",
            ):
                self.assertIn(name, output,
                              f"skills list missing {name} after init")


class TestClaudeMdSnippetReferencesWriteFact(unittest.TestCase):
    """CLAUDE.md snippet written by init must mention the new skill."""

    def test_claude_md_snippet_includes_write_fact(self):
        import os
        import subprocess
        import sys
        import tempfile

        cli = str(Path(__file__).resolve().parents[1] / "cli.py")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            vault = Path(tmp) / "vault"
            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("ICONTEXT_VAULT", None)
            subprocess.run(
                [sys.executable, cli, "init", "--vault", str(vault)],
                capture_output=True, text=True, env=env,
            )
            claude_md = home / ".claude" / "CLAUDE.md"
            self.assertTrue(claude_md.exists(), "CLAUDE.md not written by init")
            content = claude_md.read_text()
            self.assertIn("icontext-write-fact", content,
                          "CLAUDE.md snippet must reference icontext-write-fact")


if __name__ == "__main__":
    unittest.main()
