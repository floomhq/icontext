#!/usr/bin/env python3
"""icontext CLI — manage your AI context vault."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


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
        "error: vault not found. Pass --vault PATH, set ICONTEXT_VAULT, or create ~/context"
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
    sys.exit(f"error: unknown source '{source}'. Valid: gmail, linkedin")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    print(f"vault: {vault}")

    # Count files per tier
    for tier in ("shareable", "internal", "vault"):
        tier_dir = vault / tier
        if tier_dir.is_dir():
            count = sum(1 for _ in tier_dir.rglob("*") if _.is_file())
            print(f"  {tier}: {count} file(s)")

    # Show connector statuses
    cfg_path = vault / ".icontext" / "connectors.json"
    sources = ["gmail", "linkedin"]
    print()
    print("Connectors:")
    for source in sources:
        try:
            connector = _get_connector(source)
            st = connector.status(vault)
            connected = "yes" if st["connected"] else "no"
            last_sync = st.get("last_sync") or "never"
            summary = st.get("summary", "")
            print(f"  {source}: connected={connected}, last_sync={last_sync}, {summary}")
        except Exception as exc:
            print(f"  {source}: error — {exc}")

    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    connector = _get_connector(args.source)
    if args.source == "linkedin":
        pdf_path = getattr(args, "pdf", None)
        connector.connect(vault, pdf_path=pdf_path)
    else:
        connector.connect(vault)
    print(f"icontext: {args.source} connector configured.")
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
            print("No sources configured. Run: icontext connect gmail")
            return 1

    exit_code = 0
    for source in sources_to_sync:
        print(f"Syncing {source}...")
        try:
            connector = _get_connector(source)
            result = connector.sync(vault)
            print(f"  {result}")
        except Exception as exc:
            print(f"  error: {exc}")
            exit_code = 1

    if exit_code == 0 and sources_to_sync:
        print()
        print("─────────────────────────────────────────────")
        print("icontext: profile ready")
        print()
        print("Claude Code now knows who you are. To verify, open a new Claude Code")
        print('session and ask: "What do you know about me?"')
        print()
        print("Profile: ~/context/internal/profile/user.md")
        print("Refresh: icontext sync")
        print("─────────────────────────────────────────────")

    return exit_code


def cmd_search(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    try:
        from indexlib import search
    except ImportError:
        sys.exit("error: indexlib not found. Run from icontext repo root or after install.")

    results = search(vault, args.query, limit=args.limit, tier=args.tier or None)
    if not results:
        print("No results.")
        return 0
    for r in results:
        print(f"[{r.tier}] {r.path} (score: {r.score:.2f})")
        print(f"  {r.snippet}")
        print()
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    try:
        from indexlib import rebuild
    except ImportError:
        sys.exit("error: indexlib not found. Run from icontext repo root or after install.")

    print(f"Rebuilding index for {vault}...")
    count = rebuild(vault)
    print(f"Indexed {count} file(s).")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    import subprocess
    from pathlib import Path

    vault_path = args.vault or str(Path("~/context").expanduser())
    vault = Path(vault_path).expanduser().resolve()

    # 1. Create vault directory structure
    for subdir in ("shareable", "internal/profile", "vault"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    print(f"icontext: vault directory ready at {vault}")

    # 2. Git init if needed
    git_dir = vault / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init", str(vault)], check=True, capture_output=True)

        # Check git identity; set a temporary default if not configured
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, cwd=str(vault),
        )
        if not result.stdout.strip():
            subprocess.run(
                ["git", "config", "user.email", "icontext@local"],
                cwd=str(vault), capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "icontext"],
                cwd=str(vault), capture_output=True,
            )

        subprocess.run(
            ["git", "-C", str(vault), "commit", "--allow-empty", "-m", "init: icontext vault"],
            check=True,
            capture_output=True,
        )
        print("icontext: git repo initialised")

    # 3. Install icontext if not already installed
    installed_marker = vault / ".icontext-installed"
    icontext_dir = Path("~/icontext").expanduser()
    if installed_marker.exists():
        print("icontext: already installed, skipping clone/install")
    else:
        if not (icontext_dir / ".git").exists():
            print("icontext: cloning floomhq/icontext to ~/icontext...")
            subprocess.run(
                ["git", "clone", "--quiet", "https://github.com/floomhq/icontext", str(icontext_dir)],
                check=False,
            )
        install_sh = icontext_dir / "install.sh"
        if install_sh.exists():
            print("icontext: running installer...")
            subprocess.run(
                ["bash", str(install_sh), "--vault", str(vault), "--mode", "agents", "--yes"],
                check=False,
            )

    # 4. Insert CLAUDE.md snippet
    claude_md = Path("~/.claude/CLAUDE.md").expanduser()
    snippet = (
        "\n<!-- icontext -->\n"
        "## AI Context (icontext)\n"
        "Context vault is at ~/context. Profile lives at internal/profile/user.md.\n"
        "At the start of each session: if internal/profile/user.md was last modified more than 7 days ago, "
        "run `icontext sync` in the background.\n"
        "MCP tools available: search_vault, get_profile, sync_source, list_sources.\n"
        "<!-- /icontext -->\n"
    )
    if claude_md.exists():
        existing = claude_md.read_text()
    else:
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        existing = ""

    if "<!-- icontext -->" in existing:
        print("icontext: CLAUDE.md snippet already present, skipping")
    else:
        claude_md.write_text(existing + snippet)
        print("icontext: CLAUDE.md updated — Claude Code will auto-sync your profile")

    # 5. Success message
    print()
    print(f"icontext: vault ready at {vault}")
    print("icontext: CLAUDE.md updated — Claude Code will auto-sync your profile")
    print()
    print("Next:")
    print("  icontext connect gmail      # connect your Gmail")
    print("  icontext connect linkedin   # add your LinkedIn profile")
    print("  icontext sync               # build your profile now")
    return 0


def cmd_share(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    card_path = vault / "shareable" / "profile" / "context-card.md"
    if not card_path.exists():
        print("error: context card not found. Run: icontext sync")
        return 1
    print(card_path.read_text())
    print(f"Share this file: {card_path}")
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
        sys.exit("error: doctor.py not found.")

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
