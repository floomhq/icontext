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


# ---------------------------------------------------------------------------
# 3-stage pipeline: data parsing
# ---------------------------------------------------------------------------

class TestParseMessageHeaders(unittest.TestCase):

    def test_handles_folded_continuation_lines(self):
        from connectors.gmail import _parse_message_headers
        # RFC 2822 folded To: header — secondary recipients on continuation lines.
        raw = (
            b"Subject: Re: Project update\r\n"
            b"From: Alice <alice@example.com>\r\n"
            b"To: Bob <bob@example.com>,\r\n"
            b"\tCarol <carol@example.com>,\r\n"
            b" Dave <dave@example.com>\r\n"
            b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
            b"\r\n"
        )
        rec = _parse_message_headers(raw)
        self.assertEqual(rec["subject"], "Re: Project update")
        self.assertIn("alice@example.com", rec["from_addrs"])
        self.assertIn("bob@example.com", rec["to"])
        self.assertIn("carol@example.com", rec["to"])
        self.assertIn("dave@example.com", rec["to"])

    def test_handles_display_name_with_comma(self):
        from connectors.gmail import _parse_message_headers
        # "Doe, Jane" must NOT split into 'doe' and 'jane@...'
        raw = (
            b'Subject: Hi\r\n'
            b'From: "Doe, Jane" <jane@example.com>\r\n'
            b"To: bob@example.com\r\n"
            b"\r\n"
        )
        rec = _parse_message_headers(raw)
        self.assertEqual(rec["from_addrs"], ["jane@example.com"])
        # The pair preserves the full display name.
        self.assertTrue(any("Doe, Jane" in name for name, _ in rec["from_pairs"]))

    def test_extracts_cc_field(self):
        from connectors.gmail import _parse_message_headers
        raw = (
            b"Subject: Test\r\n"
            b"From: alice@example.com\r\n"
            b"To: bob@example.com\r\n"
            b"Cc: carol@example.com, dave@example.com\r\n"
            b"\r\n"
        )
        rec = _parse_message_headers(raw)
        self.assertIn("carol@example.com", rec["cc"])
        self.assertIn("dave@example.com", rec["cc"])

    def test_handles_mime_encoded_subject(self):
        from connectors.gmail import _parse_message_headers
        raw = (
            b"Subject: =?UTF-8?B?VGVzdCDDhMOWw5w=?=\r\n"
            b"From: alice@example.com\r\n"
            b"\r\n"
        )
        rec = _parse_message_headers(raw)
        # Should decode to "Test ÄÖÜ"
        self.assertIn("Test", rec["subject"])
        self.assertIn("Ä", rec["subject"])


class TestRelationshipSignal(unittest.TestCase):

    def test_filters_single_message_from_welcome_address(self):
        from connectors.gmail import _is_relationship_signal
        self.assertFalse(_is_relationship_signal(
            1, "welcome@somesaas.com", ["Welcome to SomeSaaS"],
        ))

    def test_filters_majority_welcome_subjects(self):
        from connectors.gmail import _is_relationship_signal
        self.assertFalse(_is_relationship_signal(
            3, "founder@somesaas.com",
            ["Welcome to SomeSaaS", "Verify your email", "Confirm your account"],
        ))

    def test_keeps_real_relationship_with_multiple_messages(self):
        from connectors.gmail import _is_relationship_signal
        self.assertTrue(_is_relationship_signal(
            5, "cedrik@example.com",
            ["Floom roadmap", "Re: Floom roadmap", "Demo prep", "Follow-up"],
        ))

    def test_filters_one_shot_from_any_sender(self):
        from connectors.gmail import _is_relationship_signal
        # A single message from anybody is too thin.
        self.assertFalse(_is_relationship_signal(
            1, "newperson@example.com", ["Quick question"],
        ))

    def test_keeps_known_address_with_two_substantive_messages(self):
        from connectors.gmail import _is_relationship_signal
        self.assertTrue(_is_relationship_signal(
            2, "simon@scaile.tech",
            ["Re: SCAILE board prep", "Follow-up on Tuesday"],
        ))


class TestValidateEntities(unittest.TestCase):

    def test_drops_one_shot_people(self):
        from connectors.gmail import _validate_entities
        extracted = {
            "people": [
                {"name": "Real Person", "email": "real@example.com",
                 "evidence_messages": 5},
                {"name": "One Shot", "email": "oneshot@example.com",
                 "evidence_messages": 1},
            ],
            "projects": [],
            "topics": [],
        }
        facts = {
            "own_addresses": [],
            "counterparties": [
                {"email": "real@example.com", "total": 5,
                 "inbound": 2, "outbound": 3, "last_seen": "2026-04-01"},
                {"email": "oneshot@example.com", "total": 1,
                 "inbound": 1, "outbound": 0, "last_seen": "2026-04-01"},
            ],
        }
        result = _validate_entities(extracted, facts)
        emails = [p["email"] for p in result["people"]]
        self.assertIn("real@example.com", emails)
        self.assertNotIn("oneshot@example.com", emails)

    def test_dedupes_by_email(self):
        from connectors.gmail import _validate_entities
        extracted = {
            "people": [
                {"name": "Alice A", "email": "alice@example.com",
                 "evidence_messages": 5},
                {"name": "Alice B", "email": "alice@example.com",
                 "evidence_messages": 5},
            ],
            "projects": [], "topics": [],
        }
        facts = {"own_addresses": [], "counterparties": [
            {"email": "alice@example.com", "total": 5, "inbound": 3,
             "outbound": 2, "last_seen": "2026-04-01"},
        ]}
        result = _validate_entities(extracted, facts)
        self.assertEqual(len(result["people"]), 1)

    def test_drops_projects_with_insufficient_evidence(self):
        from connectors.gmail import _validate_entities
        extracted = {
            "people": [],
            "projects": [
                {"name": "Real Project", "evidence_subjects": ["A", "B", "C"]},
                {"name": "Thin Project", "evidence_subjects": ["X"]},
                {"name": "No Evidence", "evidence_subjects": []},
            ],
            "topics": [],
        }
        facts = {"own_addresses": [], "counterparties": []}
        result = _validate_entities(extracted, facts)
        names = [p["name"] for p in result["projects"]]
        self.assertIn("Real Project", names)
        self.assertNotIn("Thin Project", names)
        self.assertNotIn("No Evidence", names)

    def test_skips_own_addresses(self):
        from connectors.gmail import _validate_entities
        extracted = {
            "people": [
                {"name": "Me", "email": "me@example.com",
                 "evidence_messages": 50},
            ],
            "projects": [], "topics": [],
        }
        facts = {"own_addresses": ["me@example.com"], "counterparties": []}
        result = _validate_entities(extracted, facts)
        self.assertEqual(result["people"], [])


class TestRenderProfileMd(unittest.TestCase):

    def test_renders_full_profile(self):
        from connectors.gmail import _render_profile_md
        profile = {
            "identity_summary": "You are Federico, building Floom.",
            "key_relationships": [
                {"name": "Cedrik", "company": "Floom", "role": "Co-founder",
                 "frequency": "weekly", "warmth": "hot", "context": "Daily collab"},
            ],
            "recurring_topics": ["Floom launch", "v26 wireframes"],
            "active_projects": [
                {"name": "Floom", "status": "shipping v26",
                 "participants": ["Cedrik", "Simon"]},
            ],
            "communication_patterns": "Mostly outbound to Floom team.",
            "pending_items": ["Foreign founder application"],
            "shareable_card": "Federico builds Floom.",
        }
        md = _render_profile_md(profile, ["Gmail"], 90, ["fede@floom.dev"], "2026-05-02")
        self.assertIn("Identity Summary", md)
        self.assertIn("You are Federico", md)
        self.assertIn("| Cedrik |", md)
        self.assertIn("Floom launch", md)
        self.assertIn("**Floom**", md)
        self.assertIn("Foreign founder application", md)

    def test_handles_empty_sections(self):
        from connectors.gmail import _render_profile_md
        profile = {
            "identity_summary": "",
            "key_relationships": [],
            "recurring_topics": [],
            "active_projects": [],
            "communication_patterns": "",
            "pending_items": [],
            "shareable_card": "",
        }
        md = _render_profile_md(profile, ["Gmail"], 90, [], "2026-05-02")
        # All sections present even when data is empty.
        self.assertIn("Identity Summary", md)
        self.assertIn("Key Relationships", md)
        self.assertIn("Active Projects", md)
        self.assertIn("Pending / Watch", md)
        self.assertIn("_(none)_", md)

    def test_card_renders_as_safe_md(self):
        from connectors.gmail import _render_card_md
        out = _render_card_md({"shareable_card": "Federico builds Floom."}, "2026-05-02")
        self.assertIn("shareable: true", out)
        self.assertIn("Federico builds Floom.", out)


class TestBuildCompactFacts(unittest.TestCase):

    def test_does_not_count_inbox_to_addresses_as_outbound(self):
        """Regression: To: addresses on inbox messages must NOT be treated as outbound."""
        from connectors.gmail import _build_compact_facts
        own = {"me@example.com"}
        # Inbox message addressed to a mailing list — it should not count
        # the list address as an outbound recipient.
        msgs = [
            {
                "direction": "inbox",
                "subject": "Newsletter from Foo",
                "from_addrs": ["foo@news.example.com"],
                "from_pairs": [("Foo News", "foo@news.example.com")],
                "to": ["me@example.com", "list@news.example.com"],
                "to_pairs": [("Me", "me@example.com"), ("List", "list@news.example.com")],
                "cc": [],
                "cc_pairs": [],
                "date": "Mon, 01 Apr 2024 12:00:00 +0000",
            },
        ]
        facts = _build_compact_facts(msgs, own, scan_days=90)
        # foo@news... should be considered (will be filtered as bot or 1-shot, but
        # the key invariant: list@news... is NOT logged as something the user sent to.
        for cp in facts["counterparties"]:
            if cp["email"] == "list@news.example.com":
                # If it shows up at all, outbound must be 0.
                self.assertEqual(cp["outbound"], 0)

    def test_counts_sent_to_addresses_as_outbound(self):
        from connectors.gmail import _build_compact_facts
        own = {"me@example.com"}
        msgs = [
            {
                "direction": "sent",
                "subject": "Project plan",
                "from_addrs": ["me@example.com"],
                "from_pairs": [("Me", "me@example.com")],
                "to": ["cedrik@example.com"],
                "to_pairs": [("Cedrik", "cedrik@example.com")],
                "cc": [], "cc_pairs": [],
                "date": "Mon, 01 Apr 2024 12:00:00 +0000",
            },
            {
                "direction": "sent",
                "subject": "Re: Project plan",
                "from_addrs": ["me@example.com"],
                "from_pairs": [("Me", "me@example.com")],
                "to": ["cedrik@example.com"],
                "to_pairs": [("Cedrik", "cedrik@example.com")],
                "cc": [], "cc_pairs": [],
                "date": "Tue, 02 Apr 2024 12:00:00 +0000",
            },
        ]
        facts = _build_compact_facts(msgs, own, scan_days=90)
        emails = {cp["email"]: cp for cp in facts["counterparties"]}
        self.assertIn("cedrik@example.com", emails)
        self.assertEqual(emails["cedrik@example.com"]["outbound"], 2)
        self.assertEqual(emails["cedrik@example.com"]["inbound"], 0)
        self.assertEqual(emails["cedrik@example.com"]["direction"], "you_send")


class TestRunPipeline(unittest.TestCase):

    def test_runs_all_three_stages_with_mocked_gemini(self):
        from connectors.gmail import run_pipeline
        # Build a fake connector that returns canned JSON for both stages.
        connector = MagicMock()
        extract_response = {
            "people": [
                {"name": "Cedrik Coelho", "email": "cedrik@example.com",
                 "company": "Floom", "evidence_messages": 6,
                 "direction": "balanced", "topics": ["Floom"]},
            ],
            "projects": [
                {"name": "Floom v26",
                 "evidence_subjects": ["Floom v26 plan", "Re: Floom v26 plan"]},
            ],
            "topics": ["Floom"],
        }
        profile_response = {
            "identity_summary": "You build Floom.",
            "key_relationships": [
                {"name": "Cedrik", "company": "Floom", "role": "Co-founder",
                 "frequency": "weekly", "warmth": "hot", "context": "Daily collab"},
            ],
            "recurring_topics": ["Floom"],
            "active_projects": [{"name": "Floom v26", "status": "shipping"}],
            "communication_patterns": "Outbound to Floom team.",
            "pending_items": [],
            "shareable_card": "Federico builds Floom.",
        }
        connector.gemini_call_with_retry.side_effect = [extract_response, profile_response]

        msgs = [
            {
                "direction": "sent",
                "subject": f"Floom v26 plan {i}",
                "from_addrs": ["me@example.com"],
                "from_pairs": [("Me", "me@example.com")],
                "to": ["cedrik@example.com"],
                "to_pairs": [("Cedrik", "cedrik@example.com")],
                "cc": [], "cc_pairs": [],
                "date": "Mon, 01 Apr 2024 12:00:00 +0000",
            } for i in range(3)
        ]
        msgs += [
            {
                "direction": "inbox",
                "subject": f"Re: Floom v26 plan {i}",
                "from_addrs": ["cedrik@example.com"],
                "from_pairs": [("Cedrik", "cedrik@example.com")],
                "to": ["me@example.com"],
                "to_pairs": [("Me", "me@example.com")],
                "cc": [], "cc_pairs": [],
                "date": "Mon, 01 Apr 2024 12:00:00 +0000",
            } for i in range(3)
        ]

        facts, validated, profile = run_pipeline(
            connector, msgs, {"me@example.com"}, scan_days=90,
        )
        self.assertEqual(connector.gemini_call_with_retry.call_count, 2)
        # Facts include the counterparty.
        cp_emails = [c["email"] for c in facts["counterparties"]]
        self.assertIn("cedrik@example.com", cp_emails)
        # Validated keeps the person.
        self.assertEqual(len(validated["people"]), 1)
        # Profile passes through.
        self.assertEqual(profile["identity_summary"], "You build Floom.")


class TestGeminiRetryWrapper(unittest.TestCase):

    def test_retries_on_transient_failure_then_succeeds(self):
        from connectors.gmail import GmailConnector
        gmail = GmailConnector()
        call_count = {"n": 0}

        def fake_synth(prompt):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("transient 503")
            return "ok"

        with patch.object(gmail, "gemini_synthesize", side_effect=fake_synth):
            with patch("connectors.base.time.sleep"):  # don't actually sleep
                result = gmail.gemini_call_with_retry("prompt", schema=None, max_retries=2)
        self.assertEqual(result, "ok")
        self.assertEqual(call_count["n"], 2)

    def test_raises_after_max_retries(self):
        from connectors.gmail import GmailConnector
        gmail = GmailConnector()

        with patch.object(gmail, "gemini_synthesize", side_effect=RuntimeError("permanent")):
            with patch("connectors.base.time.sleep"):
                with self.assertRaises(RuntimeError) as ctx:
                    gmail.gemini_call_with_retry("prompt", schema=None, max_retries=2)
        self.assertIn("permanent", str(ctx.exception))
