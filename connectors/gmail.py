"""Gmail IMAP connector for icontext."""
from __future__ import annotations

import getpass
import imaplib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from .base import BaseConnector, C, _c, _ok, _info, _warn, _err, _hr, _print


def _store_credential(service: str, account: str, password: str) -> None:
    try:
        import keyring
        keyring.set_password(service, account, password)
    except Exception:
        pass  # fall through to plaintext


def _get_credential(service: str, account: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(service, account)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Header parsing — RFC 2822 compliant via stdlib
# ---------------------------------------------------------------------------

def _parse_message_headers(raw: bytes | str) -> dict:
    """Parse RFC 2822 headers. Returns dict with from, to, cc, subject, date, from_addrs."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    # BytesParser handles folded continuation lines and MIME-encoded words.
    msg = BytesParser(policy=default_policy).parsebytes(raw)

    def _addrs(field: str) -> list[str]:
        raw_val = msg.get(field, "")
        if not raw_val:
            return []
        return [addr.lower().strip() for _, addr in getaddresses([raw_val]) if addr]

    def _pairs(field: str) -> list[tuple[str, str]]:
        raw_val = msg.get(field, "")
        if not raw_val:
            return []
        return [(name.strip(), addr.lower().strip())
                for name, addr in getaddresses([raw_val]) if addr]

    return {
        "subject": str(msg.get("Subject", "")).strip(),
        "from_raw": str(msg.get("From", "")).strip(),
        "from_addrs": _addrs("From"),
        "from_pairs": _pairs("From"),
        "to": _addrs("To"),
        "to_pairs": _pairs("To"),
        "cc": _addrs("Cc"),
        "cc_pairs": _pairs("Cc"),
        "date": str(msg.get("Date", "")).strip(),
    }


def _extract_domain(addr: str) -> str:
    parts = addr.split("@", 1)
    return parts[1] if len(parts) == 2 else ""


# ---------------------------------------------------------------------------
# Bot / SaaS welcome filters
# ---------------------------------------------------------------------------

_BOT_PATTERNS = re.compile(
    r"(noreply|no-reply|donotreply|bounce|notification|notifications|newsletter|"
    r"unsubscribe|mailer-daemon|automated|alerts?|update|digest|confirm|verify|"
    r"do-not-reply|hello@|info@|mailer@|news@|marketing@)",
    re.IGNORECASE,
)

_GENERIC_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "notifications",
    "notification", "news", "newsletter", "marketing", "support", "info",
    "hello", "contact", "team", "mail", "emails", "welcome", "billing",
    "alert", "alerts", "bounce", "mailer", "mailer-daemon", "help",
    "feedback", "system", "automated", "auto-reply", "postmaster",
    "abuse", "admin", "robot", "bot", "tracking",
}


def _is_bot(addr: str) -> bool:
    """Strict bot detection — only catches obvious automated senders."""
    if not addr or "@" not in addr:
        return True
    local = addr.split("@", 1)[0].lower()
    if local in _GENERIC_LOCAL_PARTS:
        return True
    if _BOT_PATTERNS.search(local):
        return True
    return False


_SAAS_WELCOME_PHRASES = (
    "welcome to", "verify your email", "verify your account",
    "confirm your", "your account at", "thanks for signing up",
    "set up your account", "activate your account", "complete your signup",
    "you're invited", "your invitation", "click to confirm",
    "password reset", "reset your password", "your receipt", "your invoice",
)


def _is_relationship_signal(msg_count: int, from_addr: str, subjects: list[str]) -> bool:
    """Drop senders that look like SaaS notifications or one-shot signups."""
    addr_lc = (from_addr or "").lower()
    local = addr_lc.split("@", 1)[0] if "@" in addr_lc else addr_lc

    # If the local-part is generic AND we have <3 messages, it's almost certainly noise.
    is_generic_local = (
        local in _GENERIC_LOCAL_PARTS
        or any(local.startswith(p) for p in ("noreply", "no-reply", "team", "hello", "support", "info", "welcome", "notifications"))
    )
    if is_generic_local and msg_count < 3:
        return False

    # Single-message signals from any sender are probably notifications.
    if msg_count < 2:
        return False

    # If the majority of subjects look like SaaS welcome / verification, drop.
    if subjects:
        welcome_hits = sum(
            1 for s in subjects
            if any(p in s.lower() for p in _SAAS_WELCOME_PHRASES)
        )
        if welcome_hits / len(subjects) > 0.5:
            return False

    return True


# ---------------------------------------------------------------------------
# IMAP fetch
# ---------------------------------------------------------------------------

def _fetch_folder(conn: imaplib.IMAP4_SSL, folder: str, since_date: str,
                   max_msgs: int, direction: str) -> list[dict]:
    """Fetch metadata from a folder. Each record gets a 'direction' tag."""
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
    if len(msg_ids) > max_msgs:
        msg_ids = msg_ids[-max_msgs:]

    results = []
    for msg_id in msg_ids:
        try:
            status, msg_data = conn.fetch(
                msg_id,
                "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE)])",
            )
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            record = _parse_message_headers(raw)
            record["direction"] = direction
            if record.get("subject") or record.get("from_addrs") or record.get("to"):
                results.append(record)
        except Exception:
            continue

    return results


def _find_sent_folder(conn: imaplib.IMAP4_SSL) -> str:
    candidates = ["[Gmail]/Sent Mail", "Sent", "Sent Items", "Sent Messages", "INBOX.Sent"]
    for name in candidates:
        try:
            status, _ = conn.select(name, readonly=True)
            if status == "OK":
                return name
        except Exception:
            continue
    return "[Gmail]/Sent Mail"


# ---------------------------------------------------------------------------
# Compact-fact extraction
# ---------------------------------------------------------------------------

_SUBJECT_NORMALIZE_PREFIX = re.compile(r"^(re|fwd?|fw|aw|wg)\s*:\s*", re.IGNORECASE)


def _normalize_subject(subj: str) -> str:
    cleaned = subj.strip()
    while True:
        new = _SUBJECT_NORMALIZE_PREFIX.sub("", cleaned).strip()
        if new == cleaned:
            break
        cleaned = new
    return cleaned


def _name_for(addr: str, name_hints: dict[str, str]) -> str:
    """Pick a best display name for an address from observed hints."""
    return name_hints.get(addr, "")


# Local-parts that almost always indicate a forward-to-self address.
_SELF_LOCAL_HINTS = {"fede", "federico", "fedeponte", "depontefede", "me", "self"}


def _detect_own_addresses(
    messages: list[dict], primary_addresses: set[str],
) -> set[str]:
    """Find addresses that look like the user's own (forwards-to-self).

    Heuristic: if the user's primary address appears in a sent message's From,
    treat any other To address whose local-part overlaps with the primary's
    local-part OR matches a known self-hint (fede/federico/...) as an alias.
    """
    own = {a.lower() for a in primary_addresses if a}
    if not own:
        return own

    primary_locals = {a.split("@", 1)[0].lower() for a in own}
    expanded_locals = primary_locals | _SELF_LOCAL_HINTS

    for msg in messages:
        if msg.get("direction") != "sent":
            continue
        from_addrs = {a.lower() for a in msg.get("from_addrs", [])}
        # Only trust the heuristic when this message was actually sent BY us.
        if not (from_addrs & own):
            continue
        for addr in msg.get("to", []) + msg.get("cc", []):
            addr_lc = (addr or "").lower()
            if not addr_lc or "@" not in addr_lc:
                continue
            local = addr_lc.split("@", 1)[0]
            # Match: identical local-part to primary, OR a known self-hint
            # that overlaps with the primary local-part (so 'fede' on
            # depontefede matches, but a random 'me@somewhere' doesn't).
            if local in primary_locals:
                own.add(addr_lc)
                continue
            if local in _SELF_LOCAL_HINTS and any(
                local in pl or pl in local for pl in primary_locals
            ):
                own.add(addr_lc)
    return own


def _build_compact_facts(
    all_messages: list[dict], own_addresses: set[str], scan_days: int,
) -> dict:
    """Extract structured facts. No LLM call. Direction-aware."""
    inbound_senders: Counter = Counter()
    outbound_recipients: Counter = Counter()
    name_hints: dict[str, str] = {}
    domain_counts: Counter = Counter()
    sender_subjects: defaultdict[str, list[str]] = defaultdict(list)
    recipient_subjects: defaultdict[str, list[str]] = defaultdict(list)
    sender_last_seen: dict[str, datetime] = {}
    recipient_last_seen: dict[str, datetime] = {}
    thread_subjects: Counter = Counter()
    all_subjects: list[str] = []

    for msg in all_messages:
        direction = msg.get("direction", "inbox")
        subj = msg.get("subject", "").strip()
        norm = _normalize_subject(subj)
        if norm:
            thread_subjects[norm] += 1
            all_subjects.append(subj)

        # Capture name hints from any From/To/Cc pair.
        for name, addr in (msg.get("from_pairs", []) + msg.get("to_pairs", [])
                            + msg.get("cc_pairs", [])):
            if name and addr and addr not in name_hints:
                name_hints[addr] = name

        # Parse date once for last-seen tracking.
        msg_dt: datetime | None = None
        date_str = msg.get("date", "")
        if date_str:
            # Try RFC 2822 first (IMAP path), then ISO 8601 (Composio path).
            try:
                msg_dt = parsedate_to_datetime(date_str)
            except Exception:
                msg_dt = None
            if msg_dt is None:
                try:
                    msg_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:
                    msg_dt = None

        if direction == "inbox":
            for frm in msg.get("from_addrs", []):
                if frm in own_addresses or _is_bot(frm):
                    continue
                inbound_senders[frm] += 1
                if subj:
                    sender_subjects[frm].append(subj[:140])
                if msg_dt:
                    prev = sender_last_seen.get(frm)
                    if not prev or msg_dt > prev:
                        sender_last_seen[frm] = msg_dt
                dom = _extract_domain(frm)
                if dom:
                    domain_counts[dom] += 1
        elif direction == "sent":
            for to_addr in msg.get("to", []) + msg.get("cc", []):
                if to_addr in own_addresses or _is_bot(to_addr):
                    continue
                outbound_recipients[to_addr] += 1
                if subj:
                    recipient_subjects[to_addr].append(subj[:140])
                if msg_dt:
                    prev = recipient_last_seen.get(to_addr)
                    if not prev or msg_dt > prev:
                        recipient_last_seen[to_addr] = msg_dt
                dom = _extract_domain(to_addr)
                if dom:
                    domain_counts[dom] += 1

    # Combined per-counterparty stats (inbound + outbound).
    combined: dict[str, dict] = {}
    for addr, cnt in inbound_senders.items():
        combined.setdefault(addr, {"inbound": 0, "outbound": 0, "subjects": []})
        combined[addr]["inbound"] = cnt
        combined[addr]["subjects"].extend(sender_subjects.get(addr, []))
        if addr in sender_last_seen:
            combined[addr].setdefault("last_seen", sender_last_seen[addr])
    for addr, cnt in outbound_recipients.items():
        combined.setdefault(addr, {"inbound": 0, "outbound": 0, "subjects": []})
        combined[addr]["outbound"] = cnt
        combined[addr]["subjects"].extend(recipient_subjects.get(addr, []))
        if addr in recipient_last_seen:
            ls = recipient_last_seen[addr]
            prev = combined[addr].get("last_seen")
            if not prev or ls > prev:
                combined[addr]["last_seen"] = ls

    # Filter out SaaS / one-shot noise.
    counterparties = []
    for addr, stats in combined.items():
        total = stats["inbound"] + stats["outbound"]
        if not _is_relationship_signal(total, addr, stats["subjects"]):
            continue
        last_seen = stats.get("last_seen")
        last_seen_str = last_seen.strftime("%Y-%m-%d") if last_seen else ""
        # Direction label.
        if stats["inbound"] and stats["outbound"]:
            d = "two_way"
        elif stats["outbound"] > stats["inbound"]:
            d = "you_send"
        else:
            d = "you_receive"
        counterparties.append({
            "email": addr,
            "name": name_hints.get(addr, ""),
            "domain": _extract_domain(addr),
            "inbound": stats["inbound"],
            "outbound": stats["outbound"],
            "total": total,
            "direction": d,
            "last_seen": last_seen_str,
            # Up to 8 sample subjects per person.
            "subjects": stats["subjects"][:8],
        })

    # Sort by combined evidence then outbound (sent matters more).
    counterparties.sort(key=lambda c: (-c["total"], -c["outbound"]))

    # Top normalized subjects (for project / topic inference).
    top_threads = [
        {"subject": s, "count": c}
        for s, c in thread_subjects.most_common(40)
        if c >= 1 and len(s) > 4
    ][:30]

    return {
        "scan_days": scan_days,
        "own_addresses": sorted(own_addresses),
        "total_messages": len(all_messages),
        "counterparties": counterparties[:30],
        "top_domains": [{"domain": d, "count": c}
                         for d, c in domain_counts.most_common(15)],
        "top_threads": top_threads,
        "recent_subjects": all_subjects[:120],
    }


# ---------------------------------------------------------------------------
# Stage A — Entity extraction schema + prompt
# ---------------------------------------------------------------------------

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "evidence_messages": {"type": "integer"},
                    "direction": {
                        "type": "string",
                        "enum": ["mostly_inbound", "mostly_outbound", "balanced"],
                    },
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "context": {"type": "string"},
                },
                "required": ["name", "email", "evidence_messages"],
            },
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence_subjects": {"type": "array", "items": {"type": "string"}},
                    "participants": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "evidence_subjects"],
            },
        },
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["people", "projects", "topics"],
}


def _extract_prompt(facts: dict, seed: str | None) -> str:
    seed_block = ""
    if seed:
        seed_block = (
            f"\nUSER_SEED (one-line self-description from the user — treat as ground truth "
            f"for project names and identity):\n{seed}\n"
        )
    return (
        "You extract structured entities from email metadata. "
        "Output MUST match the JSON schema. Do NOT invent people, projects, or topics — "
        "only those grounded in the data below. Skip any sender whose evidence is a single "
        "welcome / signup / verification / receipt subject.\n"
        "\n"
        "RULES:\n"
        "- Only include a person if they have >= 2 evidence_messages.\n"
        "- For projects: include any product/codebase/initiative name that appears in >= 2 "
        "distinct subjects. Look hard at top_threads and recent_subjects. Project names are "
        "usually capitalised proper nouns (e.g. Floom, Rocketlist, OpenPaper, Relay). "
        "If USER_SEED names a project, include it as long as it appears at least once in "
        "the data with corroborating evidence subjects.\n"
        "- For each project, give 2-6 evidence_subjects copied verbatim from the data.\n"
        "- direction: 'mostly_outbound' if the user sent more than received, "
        "'mostly_inbound' if received more than sent, 'balanced' otherwise.\n"
        "- name: use the display name observed in the data when available; "
        "fall back to local-part of email if no name was observed.\n"
        "- topics: short noun phrases that recur across multiple subjects.\n"
        "- For EACH person, do your best to fill role AND context using the subjects "
        "array and the email domain. role: a short phrase like 'Lawyer (immigration)', "
        "'Investor at Founders Inc', 'Ops collaborator'. context: cite a subject pattern, "
        "e.g. 'Schedules I-589 filings', 'Discusses Floom roadmap'. If the evidence is "
        "thin, fall back to listing the subject topic that connects you. Never leave "
        "role or context as empty strings.\n"
        "- Be specific. Use real names from the data. No filler.\n"
        f"{seed_block}"
        "\n"
        "DATA:\n"
        f"{json.dumps(facts, indent=2, default=str)}\n"
    )


# ---------------------------------------------------------------------------
# Stage B — Local validation
# ---------------------------------------------------------------------------

_PENDING_STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "and", "or", "with", "on", "in",
    "at", "from", "by", "is", "be", "are", "was", "were", "fix", "address",
    "resolve", "handle", "deal", "follow", "follow-up", "followup", "reply",
    "respond", "your", "my",
}


def _pending_tokens(item: str) -> set[str]:
    """Lowercase content tokens (>= 3 chars, not stopwords) for fuzzy dedup."""
    raw = re.findall(r"[A-Za-z0-9]+", (item or "").lower())
    return {t for t in raw if len(t) >= 3 and t not in _PENDING_STOPWORDS}


def _dedupe_pending(items: list[str], limit: int = 5) -> list[str]:
    """Drop pending items that describe the same underlying issue.

    Two items collide if (a) one is a case-insensitive substring of the other,
    or (b) their content-token sets overlap by >= 60% (Jaccard). Prefers the
    longer / more specific phrasing. Order-stable on the survivors.
    """
    cleaned = [i.strip() for i in (items or []) if i and i.strip()]
    if not cleaned:
        return []

    accepted: list[str] = []
    accepted_tokens: list[set[str]] = []

    for item in cleaned:
        item_lc = item.lower()
        item_tok = _pending_tokens(item)

        replaced_idx = -1
        skip = False
        for i, kept in enumerate(accepted):
            kept_lc = kept.lower()
            kept_tok = accepted_tokens[i]

            substring_hit = (item_lc in kept_lc) or (kept_lc in item_lc)
            if substring_hit:
                if len(item) > len(kept):
                    replaced_idx = i
                else:
                    skip = True
                break

            # Token-overlap fuzzy match — only meaningful if both items have
            # at least 2 content tokens.
            if len(item_tok) >= 2 and len(kept_tok) >= 2:
                inter = item_tok & kept_tok
                union = item_tok | kept_tok
                jaccard = len(inter) / len(union) if union else 0.0
                if jaccard >= 0.6:
                    if len(item) > len(kept):
                        replaced_idx = i
                    else:
                        skip = True
                    break

        if skip:
            continue
        if replaced_idx >= 0:
            accepted[replaced_idx] = item
            accepted_tokens[replaced_idx] = item_tok
            continue
        accepted.append(item)
        accepted_tokens.append(item_tok)

    return accepted[:limit]


def _validate_entities(extracted: dict, facts: dict) -> dict:
    """Drop low-confidence entities, dedupe, attach hard metrics."""
    own = set(facts.get("own_addresses", []))
    cps = {cp["email"]: cp for cp in facts.get("counterparties", [])}

    people: list[dict] = []
    seen_emails: set[str] = set()
    for p in extracted.get("people", []) or []:
        email = (p.get("email") or "").lower().strip()
        if not email or email in own or email in seen_emails:
            continue
        if _is_bot(email):
            continue
        # Cross-check evidence against local facts; if the email isn't in our
        # counterparty set OR has no real evidence, drop it.
        cp = cps.get(email)
        local_evidence = cp["total"] if cp else 0
        claimed = int(p.get("evidence_messages") or 0)
        evidence = local_evidence or claimed
        if evidence < 2:
            continue
        seen_emails.add(email)
        person = {
            "name": (p.get("name") or "").strip() or email.split("@", 1)[0],
            "email": email,
            "company": (p.get("company") or "").strip(),
            "role": (p.get("role") or "").strip(),
            "context": (p.get("context") or "").strip(),
            "topics": [t for t in (p.get("topics") or []) if t][:5],
            "evidence_messages": evidence,
            "direction": p.get("direction") or (cp.get("direction") if cp else "balanced"),
        }
        if cp:
            person["last_seen"] = cp.get("last_seen", "")
            person["inbound"] = cp.get("inbound", 0)
            person["outbound"] = cp.get("outbound", 0)
        people.append(person)

    people.sort(key=lambda x: -x["evidence_messages"])

    # Project validation: at least 2 distinct evidence subjects.
    projects: list[dict] = []
    seen_proj_names: set[str] = set()
    for proj in extracted.get("projects", []) or []:
        name = (proj.get("name") or "").strip()
        if not name or name.lower() in seen_proj_names:
            continue
        evidence_subjects = [s for s in (proj.get("evidence_subjects") or []) if s]
        if len(set(evidence_subjects)) < 2:
            continue
        seen_proj_names.add(name.lower())
        projects.append({
            "name": name,
            "description": (proj.get("description") or "").strip(),
            "evidence_subjects": evidence_subjects[:6],
            "participants": [p for p in (proj.get("participants") or []) if p][:6],
        })

    topics = []
    for t in (extracted.get("topics") or []):
        t = (t or "").strip()
        if t and t not in topics:
            topics.append(t)

    return {
        "people": people[:20],
        "projects": projects[:10],
        "topics": topics[:12],
    }


# ---------------------------------------------------------------------------
# Stage C — Profile synthesis schema + prompt
# ---------------------------------------------------------------------------

_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "identity_summary": {"type": "string"},
        "key_relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "frequency": {"type": "string"},
                    "warmth": {"type": "string", "enum": ["hot", "warm", "cold"]},
                    "context": {"type": "string"},
                },
                # role and context are REQUIRED — Stage C must always fill them
                # using subject evidence, not leave them blank.
                "required": ["name", "role", "context"],
            },
        },
        "recurring_topics": {"type": "array", "items": {"type": "string"}},
        "active_projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "participants": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        "communication_patterns": {"type": "string"},
        "pending_items": {"type": "array", "items": {"type": "string"}},
        "shareable_card": {"type": "string"},
    },
    "required": [
        "identity_summary", "key_relationships", "recurring_topics",
        "active_projects", "communication_patterns", "pending_items",
        "shareable_card",
    ],
}


def _profile_prompt(validated: dict, facts: dict, seed: str | None) -> str:
    seed_block = ""
    if seed:
        seed_block = f"\nUSER_SEED (use this to ground identity_summary and project names):\n{seed}\n"
    # Trim facts payload — top_threads + top_domains for fallback evidence,
    # plus a small slice of counterparties so Stage C can build comm-patterns
    # using real top inbound / outbound names.
    fallback = {
        "top_threads": facts.get("top_threads", [])[:25],
        "top_domains": facts.get("top_domains", [])[:10],
        "top_inbound": [
            {"name": cp.get("name") or cp["email"].split("@", 1)[0],
             "email": cp["email"], "count": cp["inbound"]}
            for cp in facts.get("counterparties", [])
            if cp.get("inbound", 0) > 0
        ][:5],
        "top_outbound": [
            {"name": cp.get("name") or cp["email"].split("@", 1)[0],
             "email": cp["email"], "count": cp["outbound"]}
            for cp in sorted(
                facts.get("counterparties", []),
                key=lambda c: -c.get("outbound", 0),
            )
            if cp.get("outbound", 0) > 0
        ][:5],
    }
    return (
        "You are writing a structured user profile for a coding assistant. "
        "The profile must read in the user's own voice — direct, concrete, no corporate filler. "
        "Output MUST match the JSON schema.\n"
        "\n"
        "VOICE RULES:\n"
        "- Plain second-person ('You email Cedrik weekly about Floom').\n"
        "- BANNED words: 'leveraging', 'leverage', 'innovating', 'pioneering', 'driving', "
        "'spearheading', 'forging strategic partnerships', 'ecosystem', 'AI-native', "
        "'cutting-edge', 'robust', 'seamless', 'empower', 'passionate about'.\n"
        "- No buzzword stacks. Short sentences. Specific names and counts.\n"
        "\n"
        "GROUNDING RULES:\n"
        "- key_relationships: one row per person in validated.people. Use evidence and "
        "direction fields. frequency: >=8 messages = 'weekly', 4-7 = 'monthly', "
        "2-3 = 'occasional'. warmth: 'hot' if outbound >= 3 OR direction='you_send' with "
        "evidence >= 3; 'warm' if any outbound or balanced; 'cold' if inbound-only.\n"
        "- For EVERY relationship row, you MUST fill BOTH role AND context. Never leave "
        "them blank. Infer them from the subjects array on each person and the email "
        "domain. Examples:\n"
        "    role examples: 'Lawyer (immigration cases)', 'Investor at Founders Inc', "
        "'Ops collaborator at Floom', 'Founder at Every', 'Engineer at Anthropic'.\n"
        "    context examples: 'Discusses I-589 filings and case updates', "
        "'Schedules calls about funding rounds', 'Coordinates Floom v26 launch'.\n"
        "  If the evidence is genuinely thin, fall back to citing the subject pattern, "
        "e.g. role='Unknown — pattern only' and context='Subjects: \"CLI release\", "
        "\"deploy issue\"'. NEVER output an empty role or context.\n"
        "- active_projects: include every entry in validated.projects. If USER_SEED names "
        "projects (e.g. Floom, Rocketlist, OpenPaper) AND the FALLBACK_THREADS contain "
        "subjects that mention those names, also list them as active projects. "
        "Use real names. Status should be a short phrase like 'shipping', 'fundraising', "
        "'in early users', based on subject evidence.\n"
        "- recurring_topics: real noun phrases from the data (e.g. 'Foreign founder application', "
        "'CLI releases', 'failed Vercel payments') — NOT single words like 'AI' or 'payment'.\n"
        "- pending_items: short, specific, name the thing. Skip generic items. Do NOT "
        "emit two items that describe the same underlying issue (e.g. 'Fix Vercel payment' "
        "and 'Address Vercel payment failure' — pick ONE, the more specific phrasing).\n"
        "- communication_patterns: 3-4 specific sentences. Cover: "
        "(1) who you initiate contact with most — name the top 2-3 outbound recipients "
        "from FALLBACK_THREADS.top_outbound; "
        "(2) who initiates contact with you most — name the top 2-3 inbound senders "
        "from FALLBACK_THREADS.top_inbound; "
        "(3) the dominant topic / domain split (e.g. 'Most outbound is product and legal "
        "coordination; most inbound is automated notifications and partner threads'); "
        "(4) response style if it can be inferred from threading (e.g. 'You usually reply "
        "within 24 hours on partner threads'). Use real names from the data.\n"
        "\n"
        "SHAREABLE CARD (strict format — max 200 words total):\n"
        "Federico will paste this into other AI sessions or send to collaborators who "
        "know nothing about him. Write in plain second-person. No corporate filler, no "
        "'passionate about', no 'pioneering'. Use his actual voice from his actual "
        "subjects.\n"
        "Required structure (use these EXACT bold labels and Markdown headings):\n"
        "    # {Name}\n"
        "\n"
        "    **Building:** {1 line — what they're working on right now, with the project name}\n"
        "    **Background:** {2 sentences — past company / role / scale}\n"
        "    **Currently focused on:** {bullet list, 3-5 items, each one line, drawn from active_projects + recurring_topics + pending_items}\n"
        "    **Best way to work with them:** {2 sentences — async vs sync, fast vs deliberate, what they delegate vs decide themselves, inferred from communication_patterns}\n"
        "No email addresses, no full names of contacts. Safe to share publicly.\n"
        f"{seed_block}"
        "\n"
        "VALIDATED DATA (people + projects after dedup and filter — every person here "
        "MUST appear as a key_relationships row with role AND context filled):\n"
        f"{json.dumps(validated, indent=2, default=str)}\n"
        "\n"
        "FALLBACK_THREADS (top normalized subjects, top inbound senders, top outbound "
        "recipients; use these to corroborate USER_SEED projects, write "
        "communication_patterns with real names, and build recurring_topics / "
        "pending_items):\n"
        f"{json.dumps(fallback, indent=2, default=str)}\n"
    )


# ---------------------------------------------------------------------------
# Markdown rendering — deterministic, no LLM parsing
# ---------------------------------------------------------------------------

def _render_profile_md(profile: dict, sources: list[str], scan_days: int,
                        accounts: list[str], today: str) -> str:
    lines: list[str] = [
        "---",
        f"source: {', '.join(sources)} (last {scan_days} days)" if scan_days else f"source: {', '.join(sources)}",
        f"accounts: {', '.join(accounts)}" if accounts else "",
        f"generated: {today}",
        "refresh: icontext sync gmail",
        "---",
        "",
        "## Identity Summary",
        "",
        profile.get("identity_summary", "").strip() or "_(no summary)_",
        "",
        "## Key Relationships",
        "",
    ]
    rels = profile.get("key_relationships") or []
    if rels:
        lines.append("| Name | Company | Role | Frequency | Warmth | Context |")
        lines.append("|------|---------|------|-----------|--------|---------|")
        for r in rels:
            lines.append(
                f"| {r.get('name','')} | {r.get('company','')} | {r.get('role','')} "
                f"| {r.get('frequency','')} | {r.get('warmth','')} | {r.get('context','')} |"
            )
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Recurring Topics")
    lines.append("")
    topics = profile.get("recurring_topics") or []
    for t in topics:
        lines.append(f"- {t}")
    if not topics:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Active Projects")
    lines.append("")
    projects = profile.get("active_projects") or []
    for p in projects:
        name = p.get("name", "")
        status = p.get("status", "")
        participants = ", ".join(p.get("participants") or [])
        bullet = f"- **{name}**"
        if status:
            bullet += f" — {status}"
        if participants:
            bullet += f" ({participants})"
        lines.append(bullet)
    if not projects:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Communication Patterns")
    lines.append("")
    lines.append(profile.get("communication_patterns", "").strip() or "_(none)_")
    lines.append("")

    lines.append("## Pending / Watch")
    lines.append("")
    pendings = profile.get("pending_items") or []
    for item in pendings:
        lines.append(f"- {item}")
    if not pendings:
        lines.append("_(none)_")
    lines.append("")

    # Drop empty meta lines (e.g., empty accounts).
    return "\n".join(line for line in lines if line is not None) + "\n"


def _render_relationships_md(profile: dict, today: str) -> str:
    rels = profile.get("key_relationships") or []
    body = ["---", "source: icontext/gmail", f"generated: {today}", "---", "",
            "## Key Relationships", ""]
    if rels:
        body.append("| Name | Company | Role | Frequency | Warmth | Context |")
        body.append("|------|---------|------|-----------|--------|---------|")
        for r in rels:
            body.append(
                f"| {r.get('name','')} | {r.get('company','')} | {r.get('role','')} "
                f"| {r.get('frequency','')} | {r.get('warmth','')} | {r.get('context','')} |"
            )
    else:
        body.append("_(none yet)_")
    body.append("")
    return "\n".join(body)


def _render_projects_md(profile: dict, today: str) -> str:
    projects = profile.get("active_projects") or []
    body = ["---", "source: icontext/gmail", f"generated: {today}", "---", "",
            "## Active Projects", ""]
    if projects:
        for p in projects:
            name = p.get("name", "")
            status = p.get("status", "")
            participants = ", ".join(p.get("participants") or [])
            bullet = f"- **{name}**"
            if status:
                bullet += f" — {status}"
            if participants:
                bullet += f" ({participants})"
            body.append(bullet)
    else:
        body.append("_(none yet)_")
    body.append("")
    return "\n".join(body)


def _render_card_md(profile: dict, today: str) -> str:
    card = (profile.get("shareable_card") or "").strip()
    return (
        "---\n"
        "shareable: true\n"
        f"generated: {today}\n"
        "source: icontext\n"
        "---\n\n"
        f"{card or '_(no card available)_'}\n"
    )


# ---------------------------------------------------------------------------
# Public pipeline entry point — usable by tests + dogfood drivers
# ---------------------------------------------------------------------------

def run_pipeline(
    connector: BaseConnector,
    all_messages: list[dict],
    own_addresses: set[str],
    scan_days: int,
    seed: str | None = None,
) -> tuple[dict, dict, dict]:
    """Run Stages A → B → C. Returns (facts, validated, profile).

    `connector` provides gemini_call_with_retry; tests can pass a mock.
    `all_messages` items must already include 'direction' ('inbox' or 'sent').
    """
    # Expand own_addresses to catch forwards-to-self (e.g. fede@floom.dev when
    # the configured account is depontefede@gmail.com). Without this, the user's
    # own forwarding aliases get treated as external recipients and pollute the
    # relationships table.
    own_addresses = _detect_own_addresses(all_messages, set(own_addresses))

    facts = _build_compact_facts(all_messages, own_addresses, scan_days)

    extract_prompt = _extract_prompt(facts, seed)
    extracted = connector.gemini_call_with_retry(extract_prompt, schema=_EXTRACT_SCHEMA)
    if not isinstance(extracted, dict):
        raise RuntimeError("Stage A did not return a dict from Gemini.")

    validated = _validate_entities(extracted, facts)

    profile_prompt = _profile_prompt(validated, facts, seed)
    profile = connector.gemini_call_with_retry(profile_prompt, schema=_PROFILE_SCHEMA)
    if not isinstance(profile, dict):
        raise RuntimeError("Stage C did not return a dict from Gemini.")

    # Post-process: collapse near-duplicate pending items (Gemini sometimes
    # emits "Fix payment for Vercel" + "Address Vercel payment failure").
    profile["pending_items"] = _dedupe_pending(profile.get("pending_items") or [])

    # Belt-and-suspenders: drop any relationship row whose email is in the
    # expanded own_addresses set. Stage C is told to skip them, but the model
    # occasionally surfaces them anyway, especially when they had heavy
    # outbound traffic (forwards-to-self look like real sent mail).
    own_lc = {a.lower() for a in own_addresses}
    profile["key_relationships"] = [
        r for r in (profile.get("key_relationships") or [])
        if (r.get("email") or "").lower() not in own_lc
    ]

    return facts, validated, profile


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

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
        _print(f"  Privacy: we read only email metadata — sender, subject, date.")
        _print(f"  Message content and attachments are never accessed or stored.")
        _print("")
        _print(_info("Tip: connect every primary inbox you use (work + side-project + personal)."))
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

            try:
                conn = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
                conn.login(addr, pwd)
                conn.logout()
                _print(_ok(f"gmail connected ({addr})"))
            except imaplib.IMAP4.error as exc:
                _print(_err(f"Login failed: {exc}"))
                _print(_warn("Make sure you copied the 16-character app password exactly (no spaces)."))
                retry = input("  Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue
            except OSError as exc:
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

            _store_credential("icontext-gmail", addr, pwd)
            accounts.append({"address": addr, "label": label})

            _print("")
            another = input(
                f"  {_c(C.CYAN, '→')} connect another inbox (work / side-project / personal)? [Y/n]: "
            ).strip().lower()
            if another == "n":
                break

        if not accounts:
            _print(_warn("No accounts configured."))
            return

        # Optional one-line seed prompt (helps Gemini ground identity).
        if not cfg.get("seed"):
            _print("")
            _print(_info("Optional: tell us about yourself in one sentence."))
            _print(_info("  e.g. 'I'm a founder building Floom and Rocketlist.'"))
            _print(_info("  This grounds the AI's synthesis. Skip with Enter."))
            seed = input("  > ").strip()
            if seed:
                cfg["seed"] = seed

        cfg["accounts"] = accounts
        cfg.setdefault("scan_days", 90)
        self.save_config(vault, cfg)
        _print(_ok(f"saved {len(accounts)} account(s) (passwords stored in OS keychain)"))
        _print(_info(f"account config (no passwords) saved to vault"))
        if cfg.get("scan_days", 90) == 90:
            _print(_info("scan window: 90 days. Bump to 180 in connectors.json for slower-moving relationships."))

    def sync(self, vault: Path) -> str:
        cfg = self.load_config(vault)
        accounts = cfg.get("accounts", [])
        if not accounts:
            raise RuntimeError(
                "No Gmail accounts configured.\n"
                "  Run: icontext connect gmail"
            )

        scan_days = int(cfg.get("scan_days", 90))
        since = datetime.now(UTC) - timedelta(days=scan_days)
        since_date = since.strftime("%d-%b-%Y")
        seed = cfg.get("seed")

        all_messages: list[dict] = []
        own_addresses: set[str] = set()

        for acct in accounts:
            addr = acct["address"]
            pwd = _get_credential("icontext-gmail", addr)
            if not pwd:
                pwd = acct.get("app_password", "")
            if not pwd:
                _print(_warn(f"no password for {addr} — run: icontext connect gmail"))
                continue
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
                inbox_msgs = _fetch_folder(conn, "INBOX", since_date, 300, "inbox")
                sent_folder = _find_sent_folder(conn)
                sent_msgs = _fetch_folder(conn, sent_folder, since_date, 200, "sent")
                total = len(inbox_msgs) + len(sent_msgs)
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
            raise RuntimeError(
                "No messages retrieved from any Gmail account.\n"
                "  Possible causes:\n"
                "    - IMAP is disabled in Gmail settings → enable at gmail.com/settings → Forwarding and POP/IMAP\n"
                "    - App password is stale — re-run: icontext connect gmail\n"
                f"    - No messages in the last {scan_days} days (scan window)"
            )

        # Run the 3-stage pipeline.
        synth_label = "synthesizing profile (3-stage)..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {synth_label}", flush=True)
        else:
            _print(_info(synth_label))

        facts, validated, profile = run_pipeline(
            self, all_messages, own_addresses, scan_days, seed=seed,
        )

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        account_list = [a["address"] for a in accounts]
        sources = ["Gmail"]

        # Render deterministically.
        full_md = _render_profile_md(profile, sources, scan_days, account_list, today)
        self.write_profile(vault, "internal/profile/user.md", full_md)
        self.write_profile(
            vault, "internal/profile/relationships.md",
            _render_relationships_md(profile, today),
        )
        self.write_profile(
            vault, "internal/profile/projects.md",
            _render_projects_md(profile, today),
        )
        self.write_profile(
            vault, "shareable/profile/context-card.md",
            _render_card_md(profile, today),
        )

        if sys.stdout.isatty():
            print(f"  {_c(C.GREEN, '✓')} profile written")
        else:
            _print(_ok("profile written"))

        # Update last_sync and commit once.
        cfg["last_sync"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save_config(vault, cfg)
        self.commit_profiles(vault)

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


# ---------------------------------------------------------------------------
# Backwards-compatible public symbols (kept for existing tests / imports)
# ---------------------------------------------------------------------------

def _extract_section(text: str, section_name: str) -> str:
    """Legacy section extractor (kept for back-compat tests). Not used in new pipeline."""
    pattern = rf"<!--\s*SECTION:\s*{re.escape(section_name)}\s*-->(.*?)<!--\s*END SECTION\s*-->"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""
