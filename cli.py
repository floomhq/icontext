#!/usr/bin/env python3
"""icontext CLI — manage your AI context vault."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


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


def _print(msg: str) -> None:
    if not sys.stdout.isatty():
        print(_strip_ansi(msg))
    else:
        print(msg)


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
    vault = _resolve_vault(args.vault)
    connector = _get_connector(args.source)
    if args.source == "linkedin":
        pdf_path = getattr(args, "pdf", None)
        connector.connect(vault, pdf_path=pdf_path)
    else:
        connector.connect(vault)
    return 0


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
    for subdir in ("shareable", "internal/profile", "vault"):
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

    # 3. Install icontext if not already installed
    installed_marker = vault / ".icontext-installed"
    icontext_dir = Path("~/icontext").expanduser()
    if installed_marker.exists():
        _print(_ok("icontext installed"))
    else:
        if not (icontext_dir / ".git").exists():
            _print(_info("cloning floomhq/icontext..."))
            _sp.run(
                ["git", "clone", "--quiet", "https://github.com/floomhq/icontext", str(icontext_dir)],
                check=False,
            )
        install_sh = icontext_dir / "install.sh"
        if install_sh.exists():
            _sp.run(
                ["bash", str(install_sh), "--vault", str(vault), "--mode", "agents", "--yes"],
                check=False,
            )
        _print(_ok("icontext installed"))

    # 4. Insert CLAUDE.md snippet
    claude_md = Path("~/.claude/CLAUDE.md").expanduser()
    snippet = (
        "\n<!-- icontext -->\n"
        "## AI Context (icontext)\n"
        f"Context vault is at {vault}. Profile lives at {vault}/internal/profile/user.md.\n"
        "At the start of each session: if the profile was last modified more than 7 days ago, "
        f"run `icontext sync --vault {vault}` in the background.\n"
        "MCP tools available: search_vault, get_profile, sync_source, list_sources.\n"
        "<!-- /icontext -->\n"
    )
    if claude_md.exists():
        existing = claude_md.read_text()
    else:
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        existing = ""

    if "<!-- icontext -->" in existing:
        _print(_ok("CLAUDE.md updated — auto-sync active"))
    else:
        claude_md.write_text(existing + snippet)
        _print(_ok("CLAUDE.md updated — auto-sync active"))

    _print(_hr())
    _print("")
    _print("  Next:")
    _print("    icontext connect gmail")
    _print("    icontext connect linkedin --pdf ~/Downloads/Profile.pdf")
    _print("    icontext sync")
    _print("")

    return 0


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
        description="icontext CLI — manage your AI context vault",
    )
    parser.add_argument("--vault", metavar="PATH", help="path to vault repo (overrides ICONTEXT_VAULT env)")

    sub = parser.add_subparsers(dest="command", metavar="command")

    # init
    p_init = sub.add_parser("init", help="set up a new vault and configure Claude Code integration")
    p_init.set_defaults(func=cmd_init)

    # status
    p_status = sub.add_parser("status", help="show vault info and connector statuses")
    p_status.set_defaults(func=cmd_status)

    # connect
    p_connect = sub.add_parser("connect", help="interactively configure a data source connector")
    p_connect.add_argument("source", choices=["gmail", "linkedin"])
    p_connect.add_argument(
        "--pdf", metavar="PATH",
        help="Path to LinkedIn profile PDF (save from linkedin.com/in/you → More → Save to PDF)",
    )
    p_connect.set_defaults(func=cmd_connect)

    # sync
    p_sync = sub.add_parser("sync", help="sync data source(s) and refresh profiles")
    p_sync.add_argument("source", nargs="?", choices=["gmail", "linkedin"], help="sync only this source (default: all configured)")
    p_sync.set_defaults(func=cmd_sync)

    # search
    p_search = sub.add_parser("search", help="search the vault index")
    p_search.add_argument("query")
    p_search.add_argument("--tier", choices=["shareable", "internal", "vault"], help="filter by tier")
    p_search.add_argument("--limit", type=int, default=5, metavar="N")
    p_search.set_defaults(func=cmd_search)

    # rebuild
    p_rebuild = sub.add_parser("rebuild", help="rebuild the SQLite FTS index")
    p_rebuild.set_defaults(func=cmd_rebuild)

    # share
    p_share = sub.add_parser("share", help="print the shareable context card to stdout")
    p_share.set_defaults(func=cmd_share)

    # doctor
    p_doctor = sub.add_parser("doctor", help="run health checks on the vault")
    p_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
