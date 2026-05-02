#!/usr/bin/env python3
"""icontext CLI — encrypted AI context vault for Claude Code, Codex, Cursor, and OpenCode."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

__version__ = "0.2.0"


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[32m"
    CYAN   = "\033[36m"
    YELLOW = "\033[33m"
    RED    = "\033[31m"
    WHITE  = "\033[97m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{C.RESET}"


def _ok(msg: str)   -> str: return f"  {_c(C.GREEN,  '✓')} {msg}"
def _info(msg: str) -> str: return f"  {_c(C.CYAN,   '→')} {msg}"
def _warn(msg: str) -> str: return f"  {_c(C.YELLOW, '!')} {msg}"
def _err(msg: str)  -> str: return f"  {_c(C.RED,    '✗')} {msg}"
def _hr()           -> str: return f"  {_c(C.DIM, '─' * 44)}"


def _strip_ansi(text: str) -> str:
    return re.sub(r'\033\[[0-9;]*m', '', text)


def _print(msg: str = "", **kwargs) -> None:
    if not sys.stdout.isatty():
        print(_strip_ansi(msg), **kwargs)
    else:
        print(msg, **kwargs)


def _header(cmd: str) -> None:
    _print("")
    _print(_hr())
    _print(f"    {_c(C.BOLD, f'icontext · {cmd}')}")
    _print(_hr())


# ---------------------------------------------------------------------------
# Vault helpers
# ---------------------------------------------------------------------------

def _resolve_vault(vault_arg: str | None) -> Path:
    if vault_arg:
        return Path(vault_arg).expanduser().resolve()
    env = os.environ.get("ICONTEXT_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    default = Path("~/context").expanduser().resolve()
    if default.exists():
        return default
    sys.exit(
        "\n"
        + _err("Vault not found.")
        + "\n\n"
        + _info("Run 'icontext init' to create your vault, or specify the path:")
        + "\n"
        + "    icontext --vault /path/to/vault <command>\n"
        + "    ICONTEXT_VAULT=/path/to/vault icontext <command>\n"
    )


def _add_scripts_to_path() -> None:
    """Add the scripts/ directory (relative to cli.py) to sys.path."""
    cli_dir = Path(__file__).resolve().parent
    scripts_dir = cli_dir / "scripts"
    if scripts_dir.is_dir() and str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    # Also support running from inside .icontext/
    parent_scripts = cli_dir.parent / "scripts"
    if parent_scripts.is_dir() and str(parent_scripts) not in sys.path:
        sys.path.insert(0, str(parent_scripts))


def _get_connector(source: str):
    """Import and return a connector instance by name."""
    cli_dir = Path(__file__).resolve().parent
    # Support running from inside .icontext/ (installed) or repo root
    connectors_dir = cli_dir / "connectors"
    if not connectors_dir.is_dir():
        connectors_dir = cli_dir.parent / "connectors"
    if str(connectors_dir.parent) not in sys.path:
        sys.path.insert(0, str(connectors_dir.parent))

    if source == "gmail":
        from connectors.gmail import GmailConnector
        return GmailConnector()
    if source == "linkedin":
        from connectors.linkedin import LinkedInConnector
        return LinkedInConnector()
    sys.exit(_err(f"unknown source '{source}'. Valid: gmail, linkedin"))


# ---------------------------------------------------------------------------
# Relative time helper
# ---------------------------------------------------------------------------

def _relative_time(iso: str | None) -> str:
    """Convert an ISO timestamp to a human-readable relative string."""
    if not iso:
        return "never"
    try:
        from datetime import UTC, datetime
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(UTC) - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m}m ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h}h ago"
        d = secs // 86400
        return f"{d}d ago"
    except Exception:
        return iso


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    if not vault.exists():
        _print(_err(f"Vault not found: {vault}"))
        _print(_info("Run 'icontext init' to create a vault, or check the path."))
        return 1

    _header("status")
    _print("")

    # Vault path
    home = str(Path("~").expanduser())
    vault_display = str(vault).replace(home, "~")
    _print(f"  {'vault':<12}{_c(C.WHITE, vault_display)}")

    # Connector statuses
    sources = ["gmail", "linkedin"]
    for source in sources:
        try:
            connector = _get_connector(source)
            st = connector.status(vault)
            connected = st["connected"]
            last_sync = _relative_time(st.get("last_sync"))
            summary = st.get("summary", "")
            # Extract display value from summary
            if source == "gmail" and connected:
                accounts_str = summary.replace(f"{summary.split(':')[0]}: ", "") if ":" in summary else summary
                # Show first address only for brevity
                first_addr = accounts_str.split(",")[0].strip()
                val = f"{first_addr}  {_c(C.DIM, '·')}  synced {last_sync}"
            elif source == "linkedin" and connected:
                pdf_name = summary.replace("pdf: ", "") if summary.startswith("pdf: ") else summary
                val = f"{pdf_name}  {_c(C.DIM, '·')}  synced {last_sync}"
            else:
                val = _c(C.DIM, "not connected")
            _print(f"  {source:<12}{val}")
        except Exception as exc:
            _print(f"  {source:<12}{_c(C.RED, str(exc))}")

    # Profile file
    profile_path = vault / "internal" / "profile" / "user.md"
    if profile_path.exists():
        size_kb = profile_path.stat().st_size / 1024
        home = str(Path("~").expanduser())
        rel = str(profile_path).replace(home, "~")
        _print(f"  {'profile':<12}{rel}  {_c(C.DIM, f'·  {size_kb:.1f}KB')}")
    else:
        _print(f"  {'profile':<12}{_c(C.DIM, 'not generated yet')}")

    # Context card
    card_path = vault / "shareable" / "profile" / "context-card.md"
    if card_path.exists():
        home = str(Path("~").expanduser())
        rel = str(card_path).replace(home, "~")
        _print(f"  {'card':<12}{rel}")
    else:
        _print(f"  {'card':<12}{_c(C.DIM, 'not generated yet')}")

    _print(_hr())
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    try:
        vault = _resolve_vault(args.vault)
        connector = _get_connector(args.source)
        if args.source == "linkedin":
            pdf_path = getattr(args, "pdf", None)
            connector.connect(vault, pdf_path=pdf_path)
        else:
            connector.connect(vault)
        return 0
    except KeyboardInterrupt:
        _print(_warn("cancelled"))
        return 1
    except Exception as e:
        _print(_err(str(e)))
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    sources_to_sync: list[str] = []

    if args.source:
        sources_to_sync = [args.source]
    else:
        # Sync all connected sources
        cfg_path = vault / ".icontext" / "connectors.json"
        if cfg_path.exists():
            import json
            cfg = json.loads(cfg_path.read_text())
            sources_to_sync = list(cfg.keys())
        if not sources_to_sync:
            _header("sync")
            _print("")
            _print(_warn("No sources configured yet."))
            _print("")
            _print(_info("Connect a source first:"))
            _print("    icontext connect gmail")
            _print("    icontext connect linkedin --pdf ~/Downloads/Profile.pdf")
            _print("")
            return 1

    _header("sync")
    _print("")

    exit_code = 0
    for source in sources_to_sync:
        _print(_info(source))
        try:
            connector = _get_connector(source)
            connector.sync(vault)
        except Exception as exc:
            _print(_err(str(exc)))
            exit_code = 1
        _print("")

    if exit_code == 0 and sources_to_sync:
        home = str(Path("~").expanduser())
        profile_path = vault / "internal" / "profile" / "user.md"
        profile_display = str(profile_path).replace(home, "~")

        _print(_ok("context card ready"))
        _print(_hr())
        _print(_ok(f"done  {_c(C.DIM, profile_display)}"))
        _print("")
        _print("  Open Claude Code and ask:")
        _print(f'    {_c(C.DIM, chr(34) + "What do you know about me?" + chr(34))}')
        _print(_hr())
        _print(_info("run `icontext doctor` to verify Claude Code has your profile"))
        _print("")

    return exit_code


def cmd_search(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    try:
        from indexlib import search
    except ImportError:
        sys.exit(_err("indexlib not found. Run from icontext repo root or after install."))

    results = search(vault, args.query, limit=args.limit, tier=args.tier or None)
    if not results:
        _print(_warn("No results."))
        return 0
    for r in results:
        _print(f"  {_c(C.CYAN, r.tier)}  {r.path}  {_c(C.DIM, f'score: {r.score:.2f}')}")
        _print(f"    {_c(C.DIM, r.snippet)}")
        _print("")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    try:
        from indexlib import rebuild
    except ImportError:
        sys.exit(_err("indexlib not found. Run from icontext repo root or after install."))

    _print(_info(f"Rebuilding index for {vault}..."))
    count = rebuild(vault)
    _print(_ok(f"Indexed {count} file(s)."))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    import subprocess as _sp

    vault_path = args.vault or str(Path("~/context").expanduser())
    vault = Path(vault_path).expanduser().resolve()
    home = str(Path("~").expanduser())
    vault_display = str(vault).replace(home, "~")

    _header("init")
    _print("")

    # 1. Create vault directory structure
    _print(_info(f"creating vault at {vault_display}"))
    for subdir in ("shareable/profile", "internal/profile", "vault"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    _print(_ok("shareable/   internal/   vault/   ready"))

    # 2. Git init if needed
    git_dir = vault / ".git"
    if not git_dir.exists():
        _sp.run(["git", "init", str(vault)], check=True, capture_output=True)

        # Check git identity; set a temporary default if not configured
        result = _sp.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, cwd=str(vault),
        )
        if not result.stdout.strip():
            _sp.run(
                ["git", "config", "user.email", "icontext@local"],
                cwd=str(vault), capture_output=True,
            )
            _sp.run(
                ["git", "config", "user.name", "icontext"],
                cwd=str(vault), capture_output=True,
            )

        _sp.run(
            ["git", "-C", str(vault), "commit", "--allow-empty", "-m", "init: icontext vault"],
            check=True,
            capture_output=True,
        )
    _print(_ok("git repo initialised"))

    # 3. Install skills (Claude Code + Cursor)
    skills_installed, skills_msgs = _install_skills()
    for msg in skills_msgs:
        _print(msg)

    # 4. Insert CLAUDE.md snippet
    _install_claude_md_snippet(vault)

    _print(_hr())
    _print("")
    _print("  Next: open Claude Code in this directory and paste:")
    _print("")
    _print(f"    {_c(C.BOLD, 'Populate my icontext profile from Gmail.')}")
    _print("")
    _print(f"  {_c(C.DIM, 'That is it. Claude will use its Gmail MCP to build your profile.')}")
    _print("")
    _print(f"  {_c(C.DIM, 'or, for headless setups (requires GEMINI_API_KEY):')}")
    _print("    icontext connect gmail")
    _print("    icontext sync")
    _print("")

    return 0


def _install_skills() -> tuple[int, list[str]]:
    """Install icontext skill files into ~/.claude/skills/ and ~/.cursor/rules/.

    Returns (count_installed, list_of_status_messages).
    """
    msgs: list[str] = []
    cli_dir = Path(__file__).resolve().parent
    skills_src = cli_dir / "skills"
    if not skills_src.is_dir():
        # Try repo-root layout when cli is symlinked
        skills_src = cli_dir.parent / "skills"
    if not skills_src.is_dir():
        msgs.append(_warn("skills/ source dir not found — skipping skill install"))
        return 0, msgs

    skill_names = ["icontext-populate-profile", "icontext-refresh-profile", "icontext-share-card"]
    claude_skills_dir = Path("~/.claude/skills").expanduser()
    cursor_rules_dir = Path("~/.cursor/rules").expanduser()
    claude_skills_dir.mkdir(parents=True, exist_ok=True)
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for name in skill_names:
        src = skills_src / name / "SKILL.md"
        if not src.exists():
            msgs.append(_warn(f"missing skill source: {src}"))
            continue

        # Claude Code: ~/.claude/skills/<name>/SKILL.md
        dest_claude = claude_skills_dir / name / "SKILL.md"
        dest_claude.parent.mkdir(parents=True, exist_ok=True)
        dest_claude.write_text(src.read_text())

        # Cursor: ~/.cursor/rules/<name>.mdc (single-file equivalent)
        dest_cursor = cursor_rules_dir / f"{name}.mdc"
        dest_cursor.write_text(src.read_text())

        count += 1

    if count > 0:
        msgs.append(_ok(f"{count} skill(s) installed (Claude Code + Cursor)"))
    return count, msgs


def _install_claude_md_snippet(vault: Path) -> None:
    """Write or update the icontext snippet in ~/.claude/CLAUDE.md."""
    claude_md = Path("~/.claude/CLAUDE.md").expanduser()
    home = str(Path("~").expanduser())
    vault_short = str(vault).replace(home, "~")

    snippet = (
        "<!-- icontext -->\n"
        "## iContext (your context vault)\n\n"
        f"Your context vault is at {vault_short} with this structure:\n\n"
        "  internal/profile/    — private synthesized profile\n"
        "    user.md            — full profile (identity, relationships, projects)\n"
        "    relationships.md   — key contacts table\n"
        "    projects.md        — active projects\n"
        "  shareable/profile/   — shareable summaries\n"
        "    context-card.md    — sendable to collaborators\n\n"
        "ALWAYS read internal/profile/user.md at session start before answering personal\n"
        "or work questions about the user.\n\n"
        "If files are missing or older than 7 days, offer to populate/refresh.\n"
        "To populate, invoke the icontext-populate-profile skill.\n\n"
        "Available skills:\n"
        "- icontext-populate-profile  (build profile from Gmail/LinkedIn/chat)\n"
        "- icontext-refresh-profile   (update stale profile)\n"
        "- icontext-share-card        (regenerate shareable summary)\n"
        "<!-- /icontext -->"
    )

    if claude_md.exists():
        existing = claude_md.read_text()
    else:
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        existing = ""

    pattern = re.compile(r"<!-- icontext -->.*?<!-- /icontext -->", re.DOTALL)
    if pattern.search(existing):
        new_text = pattern.sub(snippet, existing)
        if new_text != existing:
            claude_md.write_text(new_text)
            _print(_ok("CLAUDE.md updated (skill references refreshed)"))
        else:
            _print(_ok("CLAUDE.md already up to date"))
    else:
        sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
        claude_md.write_text(existing + sep + snippet + "\n")
        _print(_ok("CLAUDE.md updated — skills wired in"))


def cmd_share(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    card_path = vault / "shareable" / "profile" / "context-card.md"
    home = str(Path("~").expanduser())
    card_display = str(card_path).replace(home, "~")

    if not card_path.exists():
        _header("share")
        _print("")
        _print(_warn("No context card found yet."))
        _print("")
        _print("  The card is generated automatically during your first Gmail sync.")
        _print("")
        _print(_info("icontext connect gmail   # if not done yet"))
        _print(_info("icontext sync            # generates the card"))
        _print("")
        return 1

    _header("your context card")
    _print("")
    # Print card content (no color, it's markdown)
    content = card_path.read_text()
    for line in content.splitlines():
        print(f"  {line}")
    _print("")
    _print(_hr())
    _print(f"  file: {_c(C.DIM, card_display)}")
    _print("  share: email it, paste it into a new AI session,")
    _print("         or drop it into a collaborator's vault")
    _print(_hr())
    _print("")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    """List or update installed icontext skills."""
    import subprocess as _sp

    action = getattr(args, "skills_action", None) or "list"
    claude_skills_dir = Path("~/.claude/skills").expanduser()
    cursor_rules_dir = Path("~/.cursor/rules").expanduser()
    skill_names = ["icontext-populate-profile", "icontext-refresh-profile", "icontext-share-card"]

    if action == "list":
        _header("skills")
        _print("")
        for name in skill_names:
            claude_path = claude_skills_dir / name / "SKILL.md"
            cursor_path = cursor_rules_dir / f"{name}.mdc"
            claude_status = _c(C.GREEN, "✓") if claude_path.exists() else _c(C.DIM, "—")
            cursor_status = _c(C.GREEN, "✓") if cursor_path.exists() else _c(C.DIM, "—")
            _print(f"  {name:<32}  claude {claude_status}   cursor {cursor_status}")
        _print("")
        _print(_hr())
        return 0

    if action == "update":
        _header("skills · update")
        _print("")
        # Pull latest skill files from the icontext repo
        icontext_dir = Path("~/icontext").expanduser()
        if (icontext_dir / ".git").exists():
            _print(_info("pulling latest from floomhq/icontext..."))
            result = _sp.run(
                ["git", "-C", str(icontext_dir), "pull", "--ff-only", "--quiet"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                _print(_warn(f"git pull failed: {result.stderr.strip()}"))
        else:
            _print(_warn(f"no icontext repo at {icontext_dir} — using bundled skills"))

        count, msgs = _install_skills()
        for msg in msgs:
            _print(msg)
        _print("")
        _print(_hr())
        return 0 if count > 0 else 1

    _print(_err(f"unknown skills action: {action}"))
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    # Find doctor.py relative to cli.py
    cli_dir = Path(__file__).resolve().parent
    candidates = [
        cli_dir / "scripts" / "doctor.py",
        cli_dir.parent / "scripts" / "doctor.py",
        vault / ".icontext" / "scripts" / "doctor.py",
    ]
    doctor_script = next((p for p in candidates if p.exists()), None)
    if doctor_script is None:
        sys.exit(_err("doctor.py not found."))

    result = subprocess.run(
        [sys.executable, str(doctor_script), "--repo", str(vault)],
        check=False,
    )
    return result.returncode


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="icontext",
        description="Encrypted AI context vault for Claude Code, Codex, Cursor, OpenCode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  icontext init                                    # set up vault + skills\n"
            "  icontext skills list                             # show installed skills\n"
            "  icontext skills update                           # pull latest skills\n"
            "  icontext status                                  # show vault state\n"
            "  icontext search 'fundraising'\n"
            "\n"
            "headless / fallback (requires GEMINI_API_KEY):\n"
            "  icontext connect gmail\n"
            "  icontext connect linkedin --pdf ~/Downloads/Profile.pdf\n"
            "  icontext sync\n"
            "\n"
            "docs: https://icontext.dev\n"
            "issues: https://github.com/floomhq/icontext/issues"
        ),
    )
    parser.add_argument(
        "--vault", metavar="PATH",
        help="path to vault directory (overrides ICONTEXT_VAULT env var; default: ~/context)",
    )
    parser.add_argument(
        "--version", action="version", version=f"icontext {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def _add_vault_arg(p: argparse.ArgumentParser) -> None:
        # default=argparse.SUPPRESS means this won't override the parent parser's --vault
        # when the user puts --vault before the subcommand (e.g. icontext --vault PATH status)
        p.add_argument(
            "--vault", metavar="PATH", default=argparse.SUPPRESS,
            help="path to vault directory (overrides ICONTEXT_VAULT env var; default: ~/context)",
        )

    # init
    p_init = sub.add_parser(
        "init",
        help="set up a new vault and install agent skills",
        description=(
            "Create a new context vault at ~/context (or --vault PATH), initialise a git\n"
            "repo, install icontext skills for Claude Code and Cursor, and insert a snippet\n"
            "into ~/.claude/CLAUDE.md so your agent loads your profile at session start.\n"
            "\n"
            "After init, open Claude Code and say:\n"
            "  \"Populate my icontext profile\"\n"
            "\n"
            "No API keys required. Headless `icontext sync` is also available as a fallback\n"
            "(requires GEMINI_API_KEY)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_init.set_defaults(func=cmd_init)
    _add_vault_arg(p_init)

    # status
    p_status = sub.add_parser(
        "status",
        help="show vault and connector status",
        description=(
            "Print the vault path, connected sources, last sync time,\n"
            "and whether a profile and context card have been generated."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_status.set_defaults(func=cmd_status)
    _add_vault_arg(p_status)

    # connect
    p_connect = sub.add_parser(
        "connect",
        help="connect a data source (gmail, linkedin)",
        description=(
            "Interactively configure a data source connector and save credentials.\n"
            "\n"
            "  gmail    — IMAP metadata scan (subjects, senders, dates — no message bodies).\n"
            "             Requires a Gmail App Password (2FA must be enabled):\n"
            "             https://myaccount.google.com/apppasswords\n"
            "\n"
            "  linkedin — Extract professional profile from a LinkedIn PDF export.\n"
            "             Download: linkedin.com/in/you → More → Save to PDF\n"
            "             Then: icontext connect linkedin --pdf ~/Downloads/Profile.pdf"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_connect.add_argument("source", choices=["gmail", "linkedin"], metavar="SOURCE",
                           help="data source to connect: gmail or linkedin")
    p_connect.add_argument(
        "--pdf", metavar="PATH",
        help=(
            "path to your LinkedIn profile PDF — skip the interactive prompt\n"
            "  Download from: linkedin.com/in/you → More → Save to PDF"
        ),
    )
    p_connect.set_defaults(func=cmd_connect)
    _add_vault_arg(p_connect)

    # sync
    p_sync = sub.add_parser(
        "sync",
        help="optional headless sync (requires GEMINI_API_KEY)",
        description=(
            "Optional headless fallback for setups where no AI agent is available.\n"
            "Pulls fresh data from connected sources and regenerates the AI profile\n"
            "using Gemini. Requires GEMINI_API_KEY.\n"
            "\n"
            "  icontext sync              # sync all configured sources\n"
            "  icontext sync gmail        # sync Gmail only\n"
            "  icontext sync linkedin     # sync LinkedIn only\n"
            "\n"
            "For most users: open Claude Code and say \"populate my icontext profile\"\n"
            "instead. The agent uses its own tools (Gmail MCP, browser, PDF) and\n"
            "writes the same files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sync.add_argument(
        "source", nargs="?", choices=["gmail", "linkedin"], metavar="SOURCE",
        help="sync only this source; omit to sync all configured sources",
    )
    p_sync.set_defaults(func=cmd_sync)
    _add_vault_arg(p_sync)

    # search
    p_search = sub.add_parser(
        "search",
        help="search the vault",
        description=(
            "Full-text search across the vault index.\n"
            "\n"
            "  icontext search 'fundraising'\n"
            "  icontext search 'YC' --tier shareable\n"
            "  icontext search 'investors' --limit 10\n"
            "\n"
            "Tiers: shareable (public-safe), internal (private), vault (all files)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_search.add_argument("query", help="search terms")
    p_search.add_argument(
        "--tier", choices=["shareable", "internal", "vault"],
        help="restrict results to a specific tier",
    )
    p_search.add_argument("--limit", type=int, default=5, metavar="N",
                          help="maximum number of results (default: 5)")
    p_search.set_defaults(func=cmd_search)
    _add_vault_arg(p_search)

    # rebuild
    p_rebuild = sub.add_parser(
        "rebuild",
        help="rebuild the search index",
        description=(
            "Rebuild the SQLite full-text search index from scratch.\n"
            "\n"
            "Run this if search returns stale or missing results after editing\n"
            "vault files manually."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rebuild.set_defaults(func=cmd_rebuild)
    _add_vault_arg(p_rebuild)

    # share
    p_share = sub.add_parser(
        "share",
        help="print your shareable context card",
        description=(
            "Print the public-safe context card to stdout.\n"
            "\n"
            "The card is generated automatically during your first Gmail sync.\n"
            "It contains only professional, public-facing context — no email\n"
            "patterns or private relationship details.\n"
            "\n"
            "Uses: paste into a new AI session, email to a collaborator,\n"
            "or drop into a shared vault."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_share.set_defaults(func=cmd_share)
    _add_vault_arg(p_share)

    # skills
    p_skills = sub.add_parser(
        "skills",
        help="list or update installed skills",
        description=(
            "Manage the icontext skills installed for Claude Code and Cursor.\n"
            "\n"
            "  icontext skills list     # show installed skills and target tools\n"
            "  icontext skills update   # pull latest skill versions from the icontext repo\n"
            "\n"
            "Skills are Markdown instructions that your AI agent reads to populate\n"
            "and refresh your profile. They live at:\n"
            "  ~/.claude/skills/icontext-*/SKILL.md\n"
            "  ~/.cursor/rules/icontext-*.mdc"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    skills_sub = p_skills.add_subparsers(dest="skills_action", metavar="ACTION")
    skills_sub.add_parser("list", help="show installed skills")
    skills_sub.add_parser("update", help="pull latest skill versions")
    p_skills.set_defaults(func=cmd_skills)

    # doctor
    p_doctor = sub.add_parser(
        "doctor",
        help="verify install integrity",
        description=(
            "Run health checks: vault structure, connector config, CLAUDE.md snippet,\n"
            "GEMINI_API_KEY, and Python dependency versions.\n"
            "\n"
            "Run after install or when Claude Code does not seem to load your profile."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_doctor.set_defaults(func=cmd_doctor)
    _add_vault_arg(p_doctor)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
