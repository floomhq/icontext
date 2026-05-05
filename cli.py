#!/usr/bin/env python3
"""fbrain CLI: encrypted AI context vault for Claude Code, Codex, Cursor, and OpenCode."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

__version__ = "0.5.0"

CANONICAL_SKILLS = [
    "fbrain-populate-profile",
    "fbrain-refresh-profile",
    "fbrain-share-card",
    "fbrain-write-fact",
]
LEGACY_SKILLS = [
    "icontext-populate-profile",
    "icontext-refresh-profile",
    "icontext-share-card",
    "icontext-write-fact",
]


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
    _print(f"    {_c(C.BOLD, f'fbrain · {cmd}')}")
    _print(_hr())


# ---------------------------------------------------------------------------
# Vault helpers
# ---------------------------------------------------------------------------

def _resolve_vault(vault_arg: str | None) -> Path:
    if vault_arg:
        return Path(vault_arg).expanduser().resolve()
    env = os.environ.get("FBRAIN_VAULT") or os.environ.get("ICONTEXT_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    default = Path("~/context").expanduser().resolve()
    if default.exists():
        return default
    sys.exit(
        "\n"
        + _err("Vault not found.")
        + "\n\n"
        + _info("Run 'fbrain init' to create your vault, or specify the path:")
        + "\n"
        + "    fbrain --vault /path/to/vault <command>\n"
        + "    FBRAIN_VAULT=/path/to/vault fbrain <command>\n"
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
        _print(_info("Run 'fbrain init' to create a vault, or check the path."))
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
            _print("    fbrain connect gmail")
            _print("    fbrain connect linkedin --pdf ~/Downloads/Profile.pdf")
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
        _print(_info("run `fbrain doctor` to verify Claude Code has your profile"))
        _print("")

    return exit_code


def cmd_search(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    _add_scripts_to_path()

    try:
        from indexlib import search
    except ImportError:
        sys.exit(_err("indexlib not found. Run from fbrain repo root or after install."))

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
        sys.exit(_err("indexlib not found. Run from fbrain repo root or after install."))

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
                ["git", "config", "user.email", "fbrain@local"],
                cwd=str(vault), capture_output=True,
            )
            _sp.run(
                ["git", "config", "user.name", "fbrain"],
                cwd=str(vault), capture_output=True,
            )

        _sp.run(
            ["git", "-C", str(vault), "commit", "--allow-empty", "-m", "init: fbrain vault"],
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
    _print(f"    {_c(C.BOLD, 'Populate my fbrain profile from Gmail.')}")
    _print("")
    _print(f"  {_c(C.DIM, 'That is it. Claude will use its Gmail MCP to build your profile.')}")
    _print("")
    _print(f"  {_c(C.DIM, 'or, for headless setups (requires GEMINI_API_KEY):')}")
    _print("    fbrain connect gmail")
    _print("    fbrain sync")
    _print("")

    return 0


def _install_skills() -> tuple[int, list[str]]:
    """Install fbrain skill files into ~/.claude/skills/ and ~/.cursor/rules/.

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

    skill_names = CANONICAL_SKILLS + LEGACY_SKILLS
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
        msgs.append(_ok(f"{count} skill file(s) installed (Claude Code + Cursor)"))
    return count, msgs


def _install_claude_md_snippet(vault: Path) -> None:
    """Write or update the fbrain snippet in ~/.claude/CLAUDE.md."""
    claude_md = Path("~/.claude/CLAUDE.md").expanduser()
    home = str(Path("~").expanduser())
    vault_short = str(vault).replace(home, "~")

    snippet = (
        "<!-- fbrain -->\n"
        "## fbrain (your context vault)\n\n"
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
        "To populate, invoke the fbrain-populate-profile skill.\n\n"
        "Available skills:\n"
        "- fbrain-populate-profile  (build profile from Gmail/LinkedIn/chat)\n"
        "- fbrain-refresh-profile   (update stale profile)\n"
        "- fbrain-share-card        (regenerate shareable summary)\n"
        "- fbrain-write-fact        (route a fact to the correct vault location)\n\n"
        "Multi-device sync: at session start, run `fbrain pull` to fetch any updates\n"
        "from other machines. The user-prompt-submit hook does this automatically if a\n"
        "remote is configured.\n"
        "<!-- /fbrain -->"
    )

    if claude_md.exists():
        existing = claude_md.read_text()
    else:
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        existing = ""

    pattern = re.compile(r"<!-- (?:fbrain|icontext) -->.*?<!-- /(?:fbrain|icontext) -->", re.DOTALL)
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
        _print(_info("fbrain connect gmail   # if not done yet"))
        _print(_info("fbrain sync            # generates the card"))
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
    """List or update installed fbrain skills."""
    import subprocess as _sp

    action = getattr(args, "skills_action", None) or "list"
    claude_skills_dir = Path("~/.claude/skills").expanduser()
    cursor_rules_dir = Path("~/.cursor/rules").expanduser()
    skill_names = CANONICAL_SKILLS

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
        # Pull latest skill files from the fbrain repo
        fbrain_dir = Path(os.environ.get("FBRAIN_ROOT", "~/fbrain")).expanduser()
        legacy_dir = Path("~/icontext").expanduser()
        repo_dir = fbrain_dir if (fbrain_dir / ".git").exists() else legacy_dir
        if (repo_dir / ".git").exists():
            _print(_info("pulling latest from floomhq/fbrain..."))
            result = _sp.run(
                ["git", "-C", str(repo_dir), "pull", "--ff-only", "--quiet"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                _print(_warn(f"git pull failed: {result.stderr.strip()}"))
        else:
            _print(_warn(f"no fbrain repo at {fbrain_dir} — using bundled skills"))

        count, msgs = _install_skills()
        for msg in msgs:
            _print(msg)
        _print("")
        _print(_hr())
        return 0 if count > 0 else 1

    _print(_err(f"unknown skills action: {action}"))
    return 1


def _git_has_origin(vault: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(vault), "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _gh_repo_create_hint() -> str:
    return (
        "First time? Set up a private remote:\n"
        "    cd <vault> && gh repo create <user>/context --private --source=. --push\n"
        "  or, if you already have a repo:\n"
        "    cd <vault> && git remote add origin git@github.com:<user>/context.git && git push -u origin main"
    )


def cmd_push(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    if not vault.exists():
        _print(_err(f"Vault not found: {vault}"))
        return 1
    if not (vault / ".git").exists():
        _print(_err(f"Vault is not a git repo: {vault}"))
        _print(_info("Run 'fbrain init' first."))
        return 1

    _header("push")
    _print("")

    # Stage all
    subprocess.run(
        ["git", "-C", str(vault), "add", "-A"],
        check=False, capture_output=True,
    )

    # Check if anything is staged or already-committed-but-not-pushed
    status = subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    changed_lines = [ln for ln in status.stdout.splitlines() if ln.strip()]
    n_changed = len(changed_lines)

    if n_changed > 0:
        # Commit
        from datetime import datetime
        msg = f"fbrain: sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        commit = subprocess.run(
            ["git", "-C", str(vault), "commit", "-m", msg],
            capture_output=True, text=True,
        )
        if commit.returncode != 0:
            _print(_warn(f"commit failed: {commit.stderr.strip() or commit.stdout.strip()}"))
        else:
            _print(_ok(f"committed: {msg} ({n_changed} file(s) changed)"))
    else:
        _print(_info("no local changes to commit"))

    # Push
    if not _git_has_origin(vault):
        _print("")
        _print(_warn("no 'origin' remote configured"))
        _print("")
        for line in _gh_repo_create_hint().splitlines():
            _print(f"  {line}")
        _print("")
        return 1

    push = subprocess.run(
        ["git", "-C", str(vault), "push"],
        capture_output=True, text=True,
    )
    if push.returncode != 0:
        err = (push.stderr or push.stdout).strip()
        _print(_err(f"push failed: {err}"))
        if "no upstream" in err.lower() or "set-upstream" in err.lower():
            _print(_info("retrying with --set-upstream origin main..."))
            push2 = subprocess.run(
                ["git", "-C", str(vault), "push", "--set-upstream", "origin", "HEAD"],
                capture_output=True, text=True,
            )
            if push2.returncode != 0:
                _print(_err((push2.stderr or push2.stdout).strip()))
                return 1
            _print(_ok("pushed (upstream set)"))
            return 0
        return 1

    _print(_ok(f"pushed to origin"))
    if push.stdout.strip():
        for line in push.stdout.strip().splitlines()[:3]:
            _print(_c(C.DIM, f"    {line}"))
    if push.stderr.strip():
        for line in push.stderr.strip().splitlines()[:3]:
            _print(_c(C.DIM, f"    {line}"))
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    vault = _resolve_vault(args.vault)
    if not vault.exists():
        _print(_err(f"Vault not found: {vault}"))
        return 1
    if not (vault / ".git").exists():
        _print(_err(f"Vault is not a git repo: {vault}"))
        return 1

    _header("pull")
    _print("")

    if not _git_has_origin(vault):
        _print(_warn("no 'origin' remote configured — nothing to pull"))
        _print("")
        for line in _gh_repo_create_hint().splitlines():
            _print(f"  {line}")
        _print("")
        return 1

    pull = subprocess.run(
        ["git", "-C", str(vault), "pull", "--rebase", "--autostash"],
        capture_output=True, text=True,
    )
    out = (pull.stdout + pull.stderr).strip()
    if pull.returncode != 0:
        _print(_err("pull failed"))
        for line in out.splitlines()[:10]:
            _print(f"    {line}")
        if "conflict" in out.lower() or "CONFLICT" in out:
            _print("")
            _print(_warn("merge conflict — resolve manually:"))
            _print(f"    cd {vault}")
            _print("    git status              # see conflicted files")
            _print("    # edit files to resolve")
            _print("    git add <files>")
            _print("    git rebase --continue")
        return 1

    if "Already up to date" in out or "up-to-date" in out.lower():
        _print(_ok("already up to date"))
    else:
        _print(_ok("pulled latest from origin"))
        for line in out.splitlines()[:6]:
            _print(_c(C.DIM, f"    {line}"))
    return 0


# ---------------------------------------------------------------------------
# autosync
# ---------------------------------------------------------------------------

LAUNCHD_LABEL = "dev.fbrain.autosync"
SYSTEMD_SERVICE = "fbrain-autosync.service"
SYSTEMD_TIMER = "fbrain-autosync.timer"


def _launchd_plist_path() -> Path:
    return Path("~/Library/LaunchAgents/dev.fbrain.autosync.plist").expanduser()


def _launchd_log_path() -> Path:
    return Path("~/Library/Logs/fbrain.log").expanduser()


def _systemd_unit_dir() -> Path:
    return Path("~/.config/systemd/user").expanduser()


def _fbrain_bin() -> str:
    """Best-effort path to the fbrain executable for use in service files."""
    import shutil as _sh
    found = _sh.which("fbrain")
    if found:
        return found
    legacy = _sh.which("icontext")
    if legacy:
        return legacy
    # Fall back to invoking cli.py directly via the current python
    return f"{sys.executable} {Path(__file__).resolve()}"


def _autosync_start_macos(vault: Path) -> int:
    plist = _launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    log_path = _launchd_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fbrain = _fbrain_bin()
    # fbrain might be "<python> <path>/cli.py"; split it.
    program_args_xml = ""
    parts = fbrain.split()
    for part in parts:
        program_args_xml += f"        <string>{part}</string>\n"
    program_args_xml += "        <string>push</string>\n"
    program_args_xml += "        <string>--vault</string>\n"
    program_args_xml += f"        <string>{vault}</string>\n"

    plist_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{program_args_xml.rstrip()}
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>KeepAlive</key>
    <false/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""
    plist.write_text(plist_xml)
    _print(_ok(f"wrote {plist}"))

    # Unload first if already loaded (idempotent), then load
    subprocess.run(
        ["launchctl", "unload", str(plist)],
        capture_output=True,
    )
    load = subprocess.run(
        ["launchctl", "load", str(plist)],
        capture_output=True, text=True,
    )
    if load.returncode != 0:
        _print(_err(f"launchctl load failed: {(load.stderr or load.stdout).strip()}"))
        return 1
    _print(_ok(f"launchd agent loaded ({LAUNCHD_LABEL})"))
    _print(_info(f"runs every 60s; logs at {log_path}"))
    return 0


def _systemctl_user_env() -> dict:
    """Return os.environ + XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS so systemctl
    --user works in headless SSH sessions where the user's bus is set up via
    `loginctl enable-linger`. No-op if already set in env."""
    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if Path(runtime_dir).is_dir():
            env["XDG_RUNTIME_DIR"] = runtime_dir
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        runtime_dir = env.get("XDG_RUNTIME_DIR", "")
        bus_path = f"{runtime_dir}/bus" if runtime_dir else ""
        if bus_path and Path(bus_path).exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"
    return env


def _autosync_start_linux(vault: Path) -> int:
    unit_dir = _systemd_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    fbrain = _fbrain_bin()
    service_path = unit_dir / SYSTEMD_SERVICE
    timer_path = unit_dir / SYSTEMD_TIMER

    service_path.write_text(
        f"""[Unit]
Description=fbrain autosync (push vault to origin)

[Service]
Type=oneshot
ExecStart={fbrain} push --vault {vault}
"""
    )
    timer_path.write_text(
        f"""[Unit]
Description=fbrain autosync timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
Unit={SYSTEMD_SERVICE}

[Install]
WantedBy=timers.target
"""
    )
    _print(_ok(f"wrote {service_path}"))
    _print(_ok(f"wrote {timer_path}"))

    sysenv = _systemctl_user_env()

    # systemctl --user daemon-reload + enable --now
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, env=sysenv)
    enable = subprocess.run(
        ["systemctl", "--user", "enable", "--now", SYSTEMD_TIMER],
        capture_output=True, text=True, env=sysenv,
    )
    if enable.returncode != 0:
        err = (enable.stderr or enable.stdout).strip()
        _print(_err(f"systemctl enable failed: {err}"))
        if "Failed to connect to bus" in err or "no medium" in err.lower():
            _print(_warn("systemd --user not reachable from this shell"))
            _print(_info("If you are in a headless SSH session, ensure linger is enabled:"))
            _print("    loginctl enable-linger $(whoami)")
            _print(_info("Then re-run with the user bus exported:"))
            _print('    XDG_RUNTIME_DIR=/run/user/$(id -u) \\')
            _print('    DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \\')
            _print('    fbrain autosync start --vault ' + str(vault))
        return 1
    _print(_ok(f"timer enabled ({SYSTEMD_TIMER}; runs every 60s)"))
    return 0


def _autosync_stop_macos() -> int:
    plist = _launchd_plist_path()
    if not plist.exists():
        _print(_warn("autosync not configured (no plist)"))
        return 0
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    plist.unlink()
    _print(_ok(f"unloaded and removed {plist}"))
    return 0


def _autosync_stop_linux() -> int:
    timer_path = _systemd_unit_dir() / SYSTEMD_TIMER
    service_path = _systemd_unit_dir() / SYSTEMD_SERVICE
    if not timer_path.exists() and not service_path.exists():
        _print(_warn("autosync not configured (no unit files)"))
        return 0
    sysenv = _systemctl_user_env()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", SYSTEMD_TIMER],
        capture_output=True, env=sysenv,
    )
    for p in (timer_path, service_path):
        if p.exists():
            p.unlink()
            _print(_ok(f"removed {p}"))
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, env=sysenv)
    return 0


def _autosync_status_macos() -> int:
    plist = _launchd_plist_path()
    log_path = _launchd_log_path()
    if not plist.exists():
        _print(_c(C.DIM, "  status:    not running (no plist installed)"))
        return 0
    list_out = subprocess.run(
        ["launchctl", "list", LAUNCHD_LABEL],
        capture_output=True, text=True,
    )
    if list_out.returncode == 0:
        _print(_ok(f"status:    running ({LAUNCHD_LABEL})"))
    else:
        _print(_warn(f"status:    plist installed but not loaded — run 'fbrain autosync start'"))
    if log_path.exists():
        mtime = log_path.stat().st_mtime
        from datetime import datetime
        last = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        _print(_info(f"last log:  {last}  ({log_path})"))
    else:
        _print(_c(C.DIM, "  last log:  no log file yet"))
    return 0


def _autosync_status_linux() -> int:
    timer_path = _systemd_unit_dir() / SYSTEMD_TIMER
    if not timer_path.exists():
        _print(_c(C.DIM, "  status:    not running (no timer installed)"))
        return 0
    sysenv = _systemctl_user_env()
    is_active = subprocess.run(
        ["systemctl", "--user", "is-active", SYSTEMD_TIMER],
        capture_output=True, text=True, env=sysenv,
    )
    state = is_active.stdout.strip() or is_active.stderr.strip()
    if state == "active":
        _print(_ok(f"status:    active ({SYSTEMD_TIMER})"))
    else:
        _print(_warn(f"status:    {state}"))
    # Last run time
    show = subprocess.run(
        ["systemctl", "--user", "show", SYSTEMD_SERVICE,
         "--property=ExecMainExitTimestamp", "--property=Result"],
        capture_output=True, text=True, env=sysenv,
    )
    for line in show.stdout.splitlines():
        if line.strip():
            _print(_info(line.strip()))
    return 0


def cmd_autosync(args: argparse.Namespace) -> int:
    import platform
    action = getattr(args, "autosync_action", None)
    if not action:
        _print(_err("autosync requires an action: start | stop | status"))
        return 1

    is_mac = platform.system() == "Darwin"
    _header(f"autosync · {action}")
    _print("")

    if action == "start":
        vault = _resolve_vault(args.vault)
        if not vault.exists():
            _print(_err(f"Vault not found: {vault}"))
            return 1
        return _autosync_start_macos(vault) if is_mac else _autosync_start_linux(vault)

    if action == "stop":
        return _autosync_stop_macos() if is_mac else _autosync_stop_linux()

    if action == "status":
        return _autosync_status_macos() if is_mac else _autosync_status_linux()

    _print(_err(f"unknown autosync action: {action}"))
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
        prog="fbrain",
        description="Encrypted AI context vault for Claude Code, Codex, Cursor, OpenCode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  fbrain init                                    # set up vault + skills\n"
            "  fbrain skills list                             # show installed skills\n"
            "  fbrain skills update                           # pull latest skills\n"
            "  fbrain status                                  # show vault state\n"
            "  fbrain search 'fundraising'\n"
            "\n"
            "headless / fallback (requires GEMINI_API_KEY):\n"
            "  fbrain connect gmail\n"
            "  fbrain connect linkedin --pdf ~/Downloads/Profile.pdf\n"
            "  fbrain sync\n"
            "\n"
            "docs: https://floom.dev/fbrain\n"
            "issues: https://github.com/floomhq/fbrain/issues"
        ),
    )
    parser.add_argument(
        "--vault", metavar="PATH",
        help="path to vault directory (overrides FBRAIN_VAULT env var; default: ~/context)",
    )
    parser.add_argument(
        "--version", action="version", version=f"fbrain {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def _add_vault_arg(p: argparse.ArgumentParser) -> None:
        # default=argparse.SUPPRESS means this won't override the parent parser's --vault
        # when the user puts --vault before the subcommand (e.g. fbrain --vault PATH status)
        p.add_argument(
            "--vault", metavar="PATH", default=argparse.SUPPRESS,
            help="path to vault directory (overrides FBRAIN_VAULT env var; default: ~/context)",
        )

    # init
    p_init = sub.add_parser(
        "init",
        help="set up a new vault and install agent skills",
        description=(
            "Create a new context vault at ~/context (or --vault PATH), initialise a git\n"
            "repo, install fbrain skills for Claude Code and Cursor, and insert a snippet\n"
            "into ~/.claude/CLAUDE.md so your agent loads your profile at session start.\n"
            "\n"
            "After init, open Claude Code and say:\n"
            "  \"Populate my fbrain profile\"\n"
            "\n"
            "No API keys required. Headless `fbrain sync` is also available as a fallback\n"
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
            "             Then: fbrain connect linkedin --pdf ~/Downloads/Profile.pdf"
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
            "  fbrain sync              # sync all configured sources\n"
            "  fbrain sync gmail        # sync Gmail only\n"
            "  fbrain sync linkedin     # sync LinkedIn only\n"
            "\n"
            "For most users: open Claude Code and say \"populate my fbrain profile\"\n"
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
            "  fbrain search 'fundraising'\n"
            "  fbrain search 'YC' --tier shareable\n"
            "  fbrain search 'investors' --limit 10\n"
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
            "Manage the fbrain skills installed for Claude Code and Cursor.\n"
            "\n"
            "  fbrain skills list     # show installed skills and target tools\n"
            "  fbrain skills update   # pull latest skill versions from the fbrain repo\n"
            "\n"
            "Skills are Markdown instructions that your AI agent reads to populate\n"
            "and refresh your profile. They live at:\n"
            "  ~/.claude/skills/fbrain-*/SKILL.md\n"
            "  ~/.cursor/rules/fbrain-*.mdc"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    skills_sub = p_skills.add_subparsers(dest="skills_action", metavar="ACTION")
    skills_sub.add_parser("list", help="show installed skills")
    skills_sub.add_parser("update", help="pull latest skill versions")
    p_skills.set_defaults(func=cmd_skills)

    # push
    p_push = sub.add_parser(
        "push",
        help="commit and push the vault to its origin remote",
        description=(
            "Stage and commit any local changes in the vault, then push to origin.\n"
            "\n"
            "Used for multi-device sync: run on device A, then 'fbrain pull' on device B.\n"
            "If no origin remote is configured, prints setup instructions for\n"
            "'gh repo create <user>/context --private --source=. --push'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_push.set_defaults(func=cmd_push)
    _add_vault_arg(p_push)

    # pull
    p_pull = sub.add_parser(
        "pull",
        help="pull updates from origin (rebase + autostash)",
        description=(
            "Fetch and rebase the vault against origin/<current>. Local in-flight\n"
            "changes are autostashed and re-applied. On conflict, surfaces the\n"
            "files and instructs you to resolve manually."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pull.set_defaults(func=cmd_pull)
    _add_vault_arg(p_pull)

    # autosync
    p_autosync = sub.add_parser(
        "autosync",
        help="manage the background autosync agent (60s push)",
        description=(
            "Manage a background agent that runs 'fbrain push' every 60 seconds.\n"
            "\n"
            "  fbrain autosync start    # install + start the agent\n"
            "  fbrain autosync stop     # stop and remove the agent\n"
            "  fbrain autosync status   # show running state and last sync time\n"
            "\n"
            "Implementation: launchd on macOS (~/Library/LaunchAgents/), systemd user\n"
            "timer on Linux (~/.config/systemd/user/). Logs:\n"
            "  macOS: ~/Library/Logs/fbrain.log\n"
            "  Linux: journalctl --user -u fbrain-autosync.service"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    autosync_sub = p_autosync.add_subparsers(dest="autosync_action", metavar="ACTION")
    p_autosync_start = autosync_sub.add_parser("start", help="install and start the agent")
    _add_vault_arg(p_autosync_start)
    p_autosync_stop = autosync_sub.add_parser("stop", help="stop and remove the agent")
    _add_vault_arg(p_autosync_stop)
    p_autosync_status = autosync_sub.add_parser("status", help="show agent state and last sync")
    _add_vault_arg(p_autosync_status)
    p_autosync.set_defaults(func=cmd_autosync)
    _add_vault_arg(p_autosync)

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


def _deprecated_main() -> int:
    print(
        "warning: 'icontext' is deprecated, use 'fbrain' instead. "
        "This shim will be removed in v0.6.0.",
        file=sys.stderr,
    )
    return main()


if __name__ == "__main__":
    raise SystemExit(main())
