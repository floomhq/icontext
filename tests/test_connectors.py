"""Tests for the connector layer (no real network calls)."""
from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    """Create minimal vault directory structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def _make_connector_cfg(vault: Path, name: str, data: dict) -> None:
    cfg_path = vault / ".icontext" / "connectors.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    all_cfg: dict = {}
    if cfg_path.exists():
        all_cfg = json.loads(cfg_path.read_text())
    all_cfg[name] = data
    cfg_path.write_text(json.dumps(all_cfg))


# ---------------------------------------------------------------------------
# Import connectors after path is set
# ---------------------------------------------------------------------------

from connectors.base import BaseConnector
from connectors.gmail import GmailConnector, _extract_section, _store_credential, _get_credential
from connectors.linkedin import LinkedInConnector


# ---------------------------------------------------------------------------
# BaseConnector — load_config
# ---------------------------------------------------------------------------

class TestBaseConnectorLoadConfig(unittest.TestCase):

    def test_returns_empty_dict_when_no_config_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            gmail = GmailConnector()
            result = gmail.load_config(vault)
        self.assertEqual(result, {})

    def test_returns_section_for_connector(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "gmail", {"accounts": [{"address": "x@example.com"}]})
            gmail = GmailConnector()
            result = gmail.load_config(vault)
        self.assertEqual(result["accounts"][0]["address"], "x@example.com")

    def test_returns_empty_dict_for_missing_section(self):
        """File exists but has no entry for this connector."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "other_source", {"key": "val"})
            gmail = GmailConnector()
            result = gmail.load_config(vault)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# BaseConnector — save_config
# ---------------------------------------------------------------------------

class TestBaseConnectorSaveConfig(unittest.TestCase):

    def test_creates_file_with_new_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            gmail = GmailConnector()
            gmail.save_config(vault, {"accounts": [], "scan_days": 60})
            cfg_path = vault / ".icontext" / "connectors.json"
            self.assertTrue(cfg_path.exists())
            data = json.loads(cfg_path.read_text())
            self.assertEqual(data["gmail"]["scan_days"], 60)

    def test_merges_keys_correctly(self):
        """Saving two connectors should keep both without overwriting."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "linkedin", {"pdf_path": "/tmp/Profile.pdf"})
            gmail = GmailConnector()
            gmail.save_config(vault, {"accounts": [{"address": "a@b.com"}]})
            cfg_path = vault / ".icontext" / "connectors.json"
            data = json.loads(cfg_path.read_text())
        # Both keys must be present
        self.assertIn("linkedin", data)
        self.assertIn("gmail", data)
        self.assertEqual(data["linkedin"]["pdf_path"], "/tmp/Profile.pdf")
        self.assertEqual(data["gmail"]["accounts"][0]["address"], "a@b.com")

    def test_overwrites_existing_section_for_same_connector(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            gmail = GmailConnector()
            gmail.save_config(vault, {"scan_days": 30})
            gmail.save_config(vault, {"scan_days": 90})
            data = json.loads((vault / ".icontext" / "connectors.json").read_text())
        self.assertEqual(data["gmail"]["scan_days"], 90)


# ---------------------------------------------------------------------------
# BaseConnector — gemini_synthesize
# ---------------------------------------------------------------------------

class TestGeminiSynthesize(unittest.TestCase):

    def test_raises_when_api_key_unset(self):
        gmail = GmailConnector()
        env_patch = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}
        with patch.dict("os.environ", env_patch, clear=False):
            # Temporarily remove keys that may be set in the environment
            import os
            original_gemini = os.environ.pop("GEMINI_API_KEY", None)
            original_google = os.environ.pop("GOOGLE_API_KEY", None)
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    gmail.gemini_synthesize("hello")
                self.assertIn("GEMINI_API_KEY", str(ctx.exception))
            finally:
                if original_gemini is not None:
                    os.environ["GEMINI_API_KEY"] = original_gemini
                if original_google is not None:
                    os.environ["GOOGLE_API_KEY"] = original_google

    def test_raises_when_google_generativeai_not_importable(self):
        gmail = GmailConnector()
        import os
        # Ensure a key is present so we get past the key check
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key-for-test"}):
            # Block the import by replacing the module with None in sys.modules
            original = sys.modules.get("google.generativeai", "ABSENT")
            sys.modules["google.generativeai"] = None  # type: ignore[assignment]
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    gmail.gemini_synthesize("hello")
                self.assertIn("google-generativeai", str(ctx.exception))
            finally:
                if original == "ABSENT":
                    sys.modules.pop("google.generativeai", None)
                else:
                    sys.modules["google.generativeai"] = original  # type: ignore[assignment]

    def test_calls_gemini_and_returns_text(self):
        """Happy path: key present, SDK available, model returns text."""
        gmail = GmailConnector()
        mock_genai = MagicMock()
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "  synthesized output  "
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            with patch.dict("sys.modules", {"google.generativeai": mock_genai}):
                # Also patch the print side-effect inside gemini_synthesize
                with patch("builtins.print"):
                    result = gmail.gemini_synthesize("test prompt")

        self.assertEqual(result, "synthesized output")


# ---------------------------------------------------------------------------
# _extract_section
# ---------------------------------------------------------------------------

class TestExtractSection(unittest.TestCase):

    def test_extracts_content_between_markers(self):
        text = (
            "Header\n"
            "<!-- SECTION: relationships -->\n"
            "## Key Relationships\n"
            "Alice | Corp | CTO\n"
            "<!-- END SECTION -->\n"
            "Footer\n"
        )
        result = _extract_section(text, "relationships")
        self.assertIn("Key Relationships", result)
        self.assertIn("Alice", result)
        self.assertNotIn("Header", result)
        self.assertNotIn("Footer", result)

    def test_returns_empty_string_when_section_missing(self):
        text = "No section markers here."
        result = _extract_section(text, "relationships")
        self.assertEqual(result, "")

    def test_extracts_correct_section_when_multiple_present(self):
        text = (
            "<!-- SECTION: relationships -->\nALICE\n<!-- END SECTION -->\n"
            "<!-- SECTION: projects -->\nPROJECT_X\n<!-- END SECTION -->\n"
        )
        self.assertIn("ALICE", _extract_section(text, "relationships"))
        self.assertNotIn("PROJECT_X", _extract_section(text, "relationships"))
        self.assertIn("PROJECT_X", _extract_section(text, "projects"))

    def test_case_insensitive_markers(self):
        text = "<!-- section: PROJECTS -->content<!-- end section -->"
        result = _extract_section(text, "PROJECTS")
        self.assertEqual(result, "content")

    def test_strips_leading_trailing_whitespace(self):
        text = "<!-- SECTION: foo -->\n  bar  \n<!-- END SECTION -->"
        result = _extract_section(text, "foo")
        self.assertEqual(result, "bar")


# ---------------------------------------------------------------------------
# GmailConnector.status
# ---------------------------------------------------------------------------

class TestGmailConnectorStatus(unittest.TestCase):

    def test_not_connected_when_no_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            st = GmailConnector().status(vault)
        self.assertFalse(st["connected"])
        self.assertIsNone(st["last_sync"])
        self.assertIn("not configured", st["summary"])

    def test_connected_when_accounts_present(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "gmail", {
                "accounts": [{"address": "test@example.com", "label": "PRIMARY"}],
                "last_sync": "2024-01-15T10:00:00Z",
            })
            st = GmailConnector().status(vault)
        self.assertTrue(st["connected"])
        self.assertEqual(st["last_sync"], "2024-01-15T10:00:00Z")
        self.assertIn("test@example.com", st["summary"])

    def test_multiple_accounts_listed_in_summary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "gmail", {
                "accounts": [
                    {"address": "a@example.com", "label": "A"},
                    {"address": "b@example.com", "label": "B"},
                ],
            })
            st = GmailConnector().status(vault)
        self.assertTrue(st["connected"])
        self.assertIn("a@example.com", st["summary"])
        self.assertIn("b@example.com", st["summary"])


# ---------------------------------------------------------------------------
# LinkedInConnector.status
# ---------------------------------------------------------------------------

class TestLinkedInConnectorStatus(unittest.TestCase):

    def test_not_connected_when_no_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            st = LinkedInConnector().status(vault)
        self.assertFalse(st["connected"])
        self.assertIsNone(st["last_sync"])
        self.assertIn("not configured", st["summary"])

    def test_connected_when_pdf_path_present(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _make_connector_cfg(vault, "linkedin", {
                "pdf_path": "/tmp/Profile.pdf",
                "last_sync": "2024-02-01T09:30:00Z",
            })
            st = LinkedInConnector().status(vault)
        self.assertTrue(st["connected"])
        self.assertEqual(st["last_sync"], "2024-02-01T09:30:00Z")
        self.assertIn("Profile.pdf", st["summary"])


# ---------------------------------------------------------------------------
# LinkedInConnector._read_pdf_text — error when PDF tools missing
# ---------------------------------------------------------------------------

class TestReadPdfText(unittest.TestCase):

    def test_raises_informative_error_when_no_pdf_tools(self):
        """When pdftotext fails and pypdf is not importable, should raise RuntimeError."""
        import tempfile
        from connectors.linkedin import _read_pdf_text

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "test.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake content")

            # Simulate pdftotext not available (non-zero exit code)
            mock_pdftotext = MagicMock()
            mock_pdftotext.returncode = 1
            mock_pdftotext.stdout = ""

            with patch("connectors.linkedin.subprocess.run", return_value=mock_pdftotext):
                # Simulate pypdf not installed
                original = sys.modules.get("pypdf", "ABSENT")
                sys.modules["pypdf"] = None  # type: ignore[assignment]
                try:
                    with self.assertRaises(RuntimeError) as ctx:
                        _read_pdf_text(pdf)
                    msg = str(ctx.exception)
                    self.assertIn("PDF", msg)
                    # Should mention at least one install option
                    self.assertTrue(
                        "pdftotext" in msg or "pypdf" in msg,
                        f"Expected install hint in error, got: {msg}"
                    )
                finally:
                    if original == "ABSENT":
                        sys.modules.pop("pypdf", None)
                    else:
                        sys.modules["pypdf"] = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Keychain helpers — _store_credential / _get_credential
# ---------------------------------------------------------------------------

class TestKeychainHelpers(unittest.TestCase):

    def test_round_trip_when_keyring_available(self):
        """Store then retrieve should return the same password."""
        mock_keyring = MagicMock()
        stored: dict[tuple, str] = {}

        def fake_set(service, account, password):
            stored[(service, account)] = password

        def fake_get(service, account):
            return stored.get((service, account))

        mock_keyring.set_password.side_effect = fake_set
        mock_keyring.get_password.side_effect = fake_get

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            _store_credential("icontext-gmail", "user@example.com", "s3cr3t")
            result = _get_credential("icontext-gmail", "user@example.com")

        self.assertEqual(result, "s3cr3t")

    def test_get_returns_none_when_keyring_raises(self):
        """If keyring raises an exception, _get_credential should return None."""
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = Exception("keyring locked")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = _get_credential("icontext-gmail", "user@example.com")

        self.assertIsNone(result)

    def test_store_falls_through_silently_when_keyring_raises(self):
        """If keyring raises an exception, _store_credential should not propagate."""
        mock_keyring = MagicMock()
        mock_keyring.set_password.side_effect = Exception("keyring locked")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            # Should not raise
            _store_credential("icontext-gmail", "user@example.com", "s3cr3t")

    def test_get_returns_none_when_keyring_not_importable(self):
        """If keyring module is not installed at all, return None gracefully."""
        original = sys.modules.get("keyring", "ABSENT")
        sys.modules["keyring"] = None  # type: ignore[assignment]
        try:
            result = _get_credential("icontext-gmail", "user@example.com")
            self.assertIsNone(result)
        finally:
            if original == "ABSENT":
                sys.modules.pop("keyring", None)
            else:
                sys.modules["keyring"] = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
