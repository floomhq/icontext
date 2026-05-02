"""Gmail IMAP connector for icontext."""
from __future__ import annotations

import email.header
import imaplib
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .base import BaseConnector

_SYNTHESIS_PROMPT = """You are building a structured user profile for Claude Code (an AI coding assistant) about the person whose email you are analyzing. This profile is loaded at every session so the AI knows who this person is, who matters to them, what they're working on, and how they operate — without needing to be told every session.

Analyze this email metadata (subjects, senders, recipients, frequencies) and produce a structured Markdown profile:

## Identity Summary
2-3 sentences: who is this person, what do they do, what are they currently focused on (infer from email patterns).

## Key Relationships
Table: Name | Company/Domain | Role | Frequency | Warmth | Notes
- Frequency: daily/weekly/monthly
- Warmth: hot/warm/cold (infer from frequency + subject patterns)
- Notes: 1-line context (investor, partner, user, collaborator, friend)
List top 15 relationships. Exclude bots, notifications, automated emails.

## Recurring Topics
8-10 bullet points. Each: topic name — how it shows up in email patterns.

## Active Projects (inferred)
4-8 bullet points. Each: project name — what seems to be happening, who's involved.

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


class GmailConnector(BaseConnector):
    name = "gmail"

    def connect(self, vault: Path) -> None:
        print("Gmail IMAP connector setup")
        print("You need an App Password (not your main password).")
        print("Get one at: Google Account → Security → 2-Step Verification → App passwords")
        print()

        cfg = self.load_config(vault)
        accounts: list[dict] = cfg.get("accounts", [])

        while True:
            addr = input("Email address: ").strip()
            if not addr:
                print("Email address is required.")
                continue
            pwd = input("App password (16 chars, spaces ignored): ").strip().replace(" ", "")
            if not pwd:
                print("App password is required.")
                continue
            label = input("Label for this account (e.g. PRIMARY, WORK) [PRIMARY]: ").strip() or "PRIMARY"

            # Test the connection
            print(f"Testing connection to {addr}...")
            try:
                conn = imaplib.IMAP4_SSL("imap.gmail.com")
                conn.login(addr, pwd)
                conn.logout()
                print(f"Connected to {addr}")
            except Exception as exc:
                print(f"Connection failed: {exc}")
                retry = input("Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue

            accounts.append({"address": addr, "app_password": pwd, "label": label})

            another = input("Add another account? [y/N]: ").strip().lower()
            if another != "y":
                break

        if not accounts:
            print("No accounts configured.")
            return

        cfg["accounts"] = accounts
        cfg.setdefault("scan_days", 90)
        self.save_config(vault, cfg)
        print(f"Saved {len(accounts)} account(s) to config.")

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

            print(f"Connecting to {addr}...")
            try:
                conn = imaplib.IMAP4_SSL("imap.gmail.com")
                conn.login(addr, pwd)
            except Exception as exc:
                print(f"  Failed to connect to {addr}: {exc}")
                continue

            try:
                # Scan inbox
                inbox_msgs = _fetch_folder(conn, "INBOX", since_date, 300)
                print(f"  INBOX: {len(inbox_msgs)} messages")
                all_messages.extend(inbox_msgs)

                # Scan sent
                sent_folder = _find_sent_folder(conn)
                sent_msgs = _fetch_folder(conn, sent_folder, since_date, 200)
                print(f"  Sent: {len(sent_msgs)} messages")
                all_messages.extend(sent_msgs)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass

        if not all_messages:
            raise RuntimeError("No messages retrieved from any account.")

        print(f"Building summary from {len(all_messages)} messages...")
        summary = _build_summary(all_messages, own_addresses)

        # Trim to ~8000 chars for Gemini
        if len(summary) > 8000:
            summary = summary[:8000] + "\n[truncated]"

        prompt = _SYNTHESIS_PROMPT.format(summary=summary)
        print("Synthesizing profile with Gemini...")
        gemini_output = self.gemini_synthesize(prompt)

        account_list = ", ".join(a["address"] for a in accounts)
        profile = (
            f"---\n"
            f"source: Gmail (last {scan_days} days)\n"
            f"accounts: {account_list}\n"
            f"generated: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
            f"refresh: icontext sync gmail\n"
            f"---\n\n"
            f"{gemini_output}\n"
        )

        self.write_profile(vault, "internal/profile/user.md", profile)

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
