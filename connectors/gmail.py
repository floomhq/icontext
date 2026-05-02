"""Gmail IMAP connector for icontext."""
from __future__ import annotations

import email.header
import getpass
import imaplib
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .base import BaseConnector, C, _c, _ok, _info, _warn, _err, _hr, _print

_SYNTHESIS_PROMPT = """You are building a structured user profile for Claude Code (an AI coding assistant) about the person whose email you are analyzing. This profile is loaded at every session so the AI knows who this person is, who matters to them, what they're working on, and how they operate — without needing to be told every session.

Analyze this email metadata (subjects, senders, recipients, frequencies) and produce a structured Markdown profile. Use the section markers exactly as shown so the output can be parsed.

## Identity Summary
2-3 sentences: who is this person, what do they do, what are they currently focused on (infer from email patterns).

<!-- SECTION: relationships -->
## Key Relationships
Table: Name | Company/Domain | Role | Frequency | Warmth | Notes
- Frequency: daily/weekly/monthly
- Warmth: hot/warm/cold (infer from frequency + subject patterns)
- Notes: 1-line context (investor, partner, user, collaborator, friend)
List top 15 relationships. Exclude bots, notifications, automated emails.
<!-- END SECTION -->

## Recurring Topics
8-10 bullet points. Each: topic name — how it shows up in email patterns.

<!-- SECTION: projects -->
## Active Projects (inferred)
4-8 bullet points. Each: project name — what seems to be happening, who's involved.
<!-- END SECTION -->

## Communication Patterns
- Who they initiate contact with most
- Who initiates with them most
- Which accounts handle which domains

## Decision-Making Signals
What do they decide themselves vs. loop others in on? Infer from CC patterns and subject lines.

## Pending / Watch
3-5 items that seem in-flight or waiting. Format: [Topic]: [status inference]

---
Be specific. Use real names. No filler. Note uncertainty with [?].

EMAIL DATA:
{summary}"""


def _decode_header(raw: str | bytes | None) -> str:
    """Decode a MIME-encoded header value to plain text."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = email.header.decode_header(raw)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return " ".join(decoded).strip()


def _extract_address(field: str) -> str:
    """Extract bare email address from 'Name <addr>' or 'addr'."""
    m = re.search(r"<([^>]+)>", field)
    if m:
        return m.group(1).strip().lower()
    return field.strip().lower()


def _extract_domain(addr: str) -> str:
    parts = addr.split("@", 1)
    return parts[1] if len(parts) == 2 else addr


_BOT_DOMAINS = {
    "noreply", "no-reply", "donotreply", "mailer-daemon", "bounce",
    "notifications", "news", "newsletter", "marketing", "support",
    "info", "hello", "contact", "team", "mail", "emails",
}

_BOT_PATTERNS = re.compile(
    r"(noreply|no-reply|donotreply|bounce|notification|newsletter|unsubscribe|"
    r"mailer-daemon|automated|alert|update|digest|confirm|verify)",
    re.IGNORECASE,
)


def _is_bot(addr: str) -> bool:
    local = addr.split("@")[0].lower()
    if _BOT_PATTERNS.search(local):
        return True
    if _BOT_PATTERNS.search(addr):
        return True
    return False


def _fetch_folder(conn: imaplib.IMAP4_SSL, folder: str, since_date: str, max_msgs: int) -> list[dict]:
    """Fetch metadata from a folder. Returns list of {subject, from, to, date}."""
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return []
    except Exception:
        return []

    try:
        status, data = conn.search(None, f'SINCE "{since_date}"')
        if status != "OK" or not data or not data[0]:
            return []
    except Exception:
        return []

    msg_ids = data[0].split()
    # Take the most recent max_msgs
    if len(msg_ids) > max_msgs:
        msg_ids = msg_ids[-max_msgs:]

    results = []
    for msg_id in msg_ids:
        try:
            status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if isinstance(raw, bytes):
                raw_str = raw.decode("utf-8", errors="replace")
            else:
                raw_str = raw
            record: dict[str, str] = {}
            for line in raw_str.splitlines():
                if line.lower().startswith("subject:"):
                    record["subject"] = _decode_header(line[8:].strip())
                elif line.lower().startswith("from:"):
                    record["from"] = _decode_header(line[5:].strip())
                elif line.lower().startswith("to:"):
                    record["to"] = _decode_header(line[3:].strip())
                elif line.lower().startswith("date:"):
                    record["date"] = line[5:].strip()
            if record:
                results.append(record)
        except Exception:
            continue

    return results


def _find_sent_folder(conn: imaplib.IMAP4_SSL) -> str:
    """Try common Sent folder names."""
    candidates = ["[Gmail]/Sent Mail", "Sent", "Sent Items", "Sent Messages", "INBOX.Sent"]
    for name in candidates:
        try:
            status, _ = conn.select(name, readonly=True)
            if status == "OK":
                return name
        except Exception:
            continue
    return "[Gmail]/Sent Mail"


def _build_summary(all_messages: list[dict], own_addresses: set[str]) -> str:
    """Build a compact text summary of email patterns for Gemini."""
    sender_counter: Counter = Counter()
    recipient_counter: Counter = Counter()
    subjects: list[str] = []

    for msg in all_messages:
        frm = _extract_address(msg.get("from", ""))
        if frm and not _is_bot(frm) and frm not in own_addresses:
            sender_counter[frm] += 1

        to_raw = msg.get("to", "")
        for part in to_raw.split(","):
            addr = _extract_address(part.strip())
            if addr and not _is_bot(addr) and addr not in own_addresses:
                recipient_counter[addr] += 1

        subj = msg.get("subject", "").strip()
        if subj and len(subj) > 3:
            subjects.append(subj[:120])

    top_senders = sender_counter.most_common(20)
    top_recipients = recipient_counter.most_common(20)
    subject_sample = subjects[:150]

    lines = [
        f"Total messages analyzed: {len(all_messages)}",
        f"Own email addresses: {', '.join(sorted(own_addresses))}",
        "",
        "Top 20 senders (address: count):",
    ]
    for addr, count in top_senders:
        lines.append(f"  {addr}: {count}")

    lines.append("")
    lines.append("Top 20 recipients you sent to (address: count):")
    for addr, count in top_recipients:
        lines.append(f"  {addr}: {count}")

    lines.append("")
    lines.append(f"Sample of {len(subject_sample)} recent subjects:")
    for subj in subject_sample:
        lines.append(f"  - {subj}")

    return "\n".join(lines)


def _extract_section(text: str, section_name: str) -> str:
    """Extract content between <!-- SECTION: name --> and <!-- END SECTION --> markers."""
    import re as _re
    pattern = rf"<!--\s*SECTION:\s*{_re.escape(section_name)}\s*-->(.*?)<!--\s*END SECTION\s*-->"
    m = _re.search(pattern, text, _re.DOTALL | _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


class GmailConnector(BaseConnector):
    name = "gmail"

    def connect(self, vault: Path) -> None:
        _print("")
        _print(_hr())
        _print(f"    {_c(C.BOLD, 'icontext · connect gmail')}")
        _print(_hr())
        _print("")
        _print(f"  Gmail requires an App Password.")
        _print("")
        _print(f"  {_c(C.BOLD, 'Step 1')} — Enable 2-Step Verification:")
        _print(_info("https://myaccount.google.com/signinoptions/two-step-verification"))
        _print("")
        _print(f"  {_c(C.BOLD, 'Step 2')} — Create App Password:")
        _print(_info("https://myaccount.google.com/apppasswords"))
        _print(_info("App name: icontext → click Create → copy 16-char code"))
        _print("")
        _print(_warn("Work/school accounts may have App Passwords disabled."))
        _print(f"    Use a personal Gmail if so.")
        _print("")
        input(f"  Press Enter when ready...")
        _print("")

        cfg = self.load_config(vault)
        accounts: list[dict] = cfg.get("accounts", [])

        while True:
            addr = input("  Gmail address: ").strip()
            if not addr:
                _print(_err("Email address is required."))
                continue
            pwd = getpass.getpass("  App password (16 chars): ").replace(" ", "")
            if not pwd:
                _print(_err("App password is required."))
                continue
            label = input("  Label (e.g. PRIMARY, WORK — or just press Enter): ").strip() or "PRIMARY"

            # Test the connection (30-second timeout covers slow network + bad credentials)
            try:
                conn = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
                conn.login(addr, pwd)
                conn.logout()
                _print(_ok(f"gmail connected ({addr})"))
            except imaplib.IMAP4.error as exc:
                # IMAP-level auth error — likely wrong app password
                _print(_err(f"Login failed: {exc}"))
                _print(_warn("Make sure you copied the 16-character app password exactly (no spaces)."))
                retry = input("  Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue
            except OSError as exc:
                # Network / DNS / timeout
                _print(_err(f"Network error: {exc}"))
                _print(_warn("Check your internet connection and try again."))
                retry = input("  Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue
            except Exception as exc:
                _print(_err(f"Connection failed: {exc}"))
                retry = input("  Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue

            accounts.append({"address": addr, "app_password": pwd, "label": label})

            another = input(f"  {_c(C.CYAN, '→')} add another account? [y/N]: ").strip().lower()
            if another != "y":
                break

        if not accounts:
            _print(_warn("No accounts configured."))
            return

        cfg["accounts"] = accounts
        cfg.setdefault("scan_days", 90)
        self.save_config(vault, cfg)
        cfg_path = vault / ".icontext" / "connectors.json"
        _print(_ok(f"saved {len(accounts)} account(s)"))
        _print(_warn(f"credentials stored in {cfg_path}"))
        _print(f"    Keep this vault out of public git repositories.")

    def sync(self, vault: Path) -> str:
        cfg = self.load_config(vault)
        accounts = cfg.get("accounts", [])
        if not accounts:
            raise RuntimeError("No Gmail accounts configured. Run: icontext connect gmail")

        scan_days = int(cfg.get("scan_days", 90))
        since = datetime.now(UTC) - timedelta(days=scan_days)
        since_date = since.strftime("%d-%b-%Y")

        all_messages: list[dict] = []
        own_addresses: set[str] = set()

        for acct in accounts:
            addr = acct["address"]
            pwd = acct["app_password"]
            own_addresses.add(addr.lower())

            label_width = 36
            label = f"connecting to {addr}..."
            if sys.stdout.isatty():
                print(f"  {_c(C.CYAN, '→')} {label:<{label_width}}", end="", flush=True)
            else:
                _print(_info(label))
            try:
                conn = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
                conn.login(addr, pwd)
                if sys.stdout.isatty():
                    print(f" {_c(C.GREEN, '✓')}")
            except imaplib.IMAP4.error as exc:
                if sys.stdout.isatty():
                    print(f" {_c(C.RED, '✗')}")
                _print(_err(f"Login failed for {addr}: {exc}"))
                _print(_warn(f"Re-run 'icontext connect gmail' to update the app password."))
                continue
            except OSError as exc:
                if sys.stdout.isatty():
                    print(f" {_c(C.RED, '✗')}")
                _print(_err(f"Network error connecting to {addr}: {exc}"))
                continue
            except Exception as exc:
                if sys.stdout.isatty():
                    print(f" {_c(C.RED, '✗')}")
                _print(_err(f"Failed to connect to {addr}: {exc}"))
                continue

            try:
                # Scan inbox
                inbox_msgs = _fetch_folder(conn, "INBOX", since_date, 300)
                total = len(inbox_msgs)

                # Scan sent
                sent_folder = _find_sent_folder(conn)
                sent_msgs = _fetch_folder(conn, sent_folder, since_date, 200)
                total += len(sent_msgs)
                all_messages.extend(inbox_msgs)
                all_messages.extend(sent_msgs)

                scan_label = f"scanning {total} messages..."
                if sys.stdout.isatty():
                    print(f"  {_c(C.CYAN, '→')} {scan_label:<{label_width}} {_c(C.GREEN, '✓')}")
                else:
                    _print(_ok(f"scanned {total} messages"))
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass

        if not all_messages:
            raise RuntimeError("No messages retrieved from any account.")

        summary = _build_summary(all_messages, own_addresses)

        # Trim to ~8000 chars for Gemini
        if len(summary) > 8000:
            summary = summary[:8000] + "\n[truncated]"

        prompt = _SYNTHESIS_PROMPT.format(summary=summary)

        synth_label = "synthesizing with Gemini..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {synth_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(synth_label))

        import subprocess as _sp
        sidecar_check = _sp.run(["which", "ai-sidecar"], capture_output=True)
        if sidecar_check.returncode != 0:
            if sys.stdout.isatty():
                print(f" {_c(C.RED, '✗')}")
            raise RuntimeError(
                "ai-sidecar not found. Install it first:\n"
                "  See: https://github.com/floomhq/icontext#requirements"
            )
        result = _sp.run(
            ["ai-sidecar", "gemini", "--model", "gemini-2.5-flash", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            if sys.stdout.isatty():
                print(f" {_c(C.RED, '✗')}")
            raise RuntimeError(f"Gemini synthesis failed: {result.stderr[:500]}")
        gemini_output = result.stdout.strip()
        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")

        if not gemini_output.strip():
            raise RuntimeError(
                "Gemini returned an empty response. Try again with: icontext sync gmail"
            )

        write_label = "writing profile..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {write_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(write_label))

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        account_list = ", ".join(a["address"] for a in accounts)
        profile = (
            f"---\n"
            f"source: Gmail (last {scan_days} days)\n"
            f"accounts: {account_list}\n"
            f"generated: {today}\n"
            f"refresh: icontext sync gmail\n"
            f"---\n\n"
            f"{gemini_output}\n"
        )

        self.write_profile(vault, "internal/profile/user.md", profile)

        # Write modular section files
        relationships_text = _extract_section(gemini_output, "relationships")
        if relationships_text:
            self.write_profile(
                vault, "internal/profile/relationships.md",
                f"---\nsource: icontext/gmail\ngenerated: {today}\n---\n\n{relationships_text}\n",
            )

        projects_text = _extract_section(gemini_output, "projects")
        if projects_text:
            self.write_profile(
                vault, "internal/profile/projects.md",
                f"---\nsource: icontext/gmail\ngenerated: {today}\n---\n\n{projects_text}\n",
            )

        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")
        else:
            _print(_ok("profile written"))

        # Write shareable context card
        card_label = "writing context card..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {card_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(card_label))

        card_prompt = (
            "From this user profile, write a short shareable context card (under 200 words) "
            "that is safe to share with collaborators. Include: who they are, what they're "
            "working on, their background. No email patterns, no private relationship details. "
            "Just professional public-facing context.\n\nPROFILE:\n" + gemini_output
        )
        try:
            card_result = _sp.run(
                ["ai-sidecar", "gemini", "--model", "gemini-2.5-flash", card_prompt],
                capture_output=True, text=True, timeout=120,
            )
            card_content = card_result.stdout.strip() if card_result.returncode == 0 else ""
            if card_content.strip():
                self.write_profile(
                    vault, "shareable/profile/context-card.md",
                    f"---\nshareable: true\ngenerated: {today}\nsource: icontext\n---\n\n{card_content}\n",
                )
                if sys.stdout.isatty():
                    print(f" {_c(C.GREEN, '✓')}")
                else:
                    _print(_ok("context card written"))
            else:
                if sys.stdout.isatty():
                    print(f" {_c(C.YELLOW, '!')}")
                _print(_warn("context card skipped (empty response)"))
        except Exception as exc:
            if sys.stdout.isatty():
                print(f" {_c(C.YELLOW, '!')}")
            _print(_warn(f"could not generate context card: {exc}"))

        # Update last_sync in config
        cfg["last_sync"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save_config(vault, cfg)

        return f"Gmail sync complete: {len(all_messages)} messages from {len(accounts)} account(s)"

    def status(self, vault: Path) -> dict:
        cfg = self.load_config(vault)
        accounts = cfg.get("accounts", [])
        connected = len(accounts) > 0
        last_sync = cfg.get("last_sync")
        if accounts:
            summary = f"{len(accounts)} account(s): " + ", ".join(a["address"] for a in accounts)
        else:
            summary = "not configured"
        return {"connected": connected, "last_sync": last_sync, "summary": summary}
