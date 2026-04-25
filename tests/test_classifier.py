import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_tiers import check_paths, load_config, tier_for_path
from icontext_classify import classify


class IcontextClassifierTests(unittest.TestCase):
    def test_secret_content_requires_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "internal" / "note.md"
            path.parent.mkdir()
            path.write_text("api_key = abc123\n", encoding="utf-8")

            result = classify("internal/note.md", root)

        self.assertEqual(result.tier, "vault")

    def test_internal_path_classifies_internal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "projects" / "roadmap.md"
            path.parent.mkdir()
            path.write_text("launch notes\n", encoding="utf-8")

            result = classify("projects/roadmap.md", root)

        self.assertEqual(result.tier, "internal")

    def test_tier_config_parser_and_matching(self):
        config = ROOT / "config" / "tiers.yml"
        tiers, enforce = load_config(config)

        self.assertFalse(enforce)
        self.assertEqual(tier_for_path("vault/secrets.md", tiers), "vault")
        self.assertEqual(tier_for_path("shareable/post.md", tiers), "shareable")
        self.assertIsNone(tier_for_path("legacy/post.md", tiers))

    def test_check_blocks_sensitive_file_in_shareable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shareable").mkdir()
            (root / "shareable" / "note.md").write_text(
                "password: abc123\n", encoding="utf-8"
            )

            with redirect_stderr(StringIO()):
                status = check_paths(
                    root, ROOT / "config" / "tiers.yml", ["shareable/note.md"]
                )

        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
