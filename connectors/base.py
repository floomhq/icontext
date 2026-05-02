"""Base connector interface for icontext data sources."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import UTC, datetime
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


# ---------------------------------------------------------------------------
# Base connector
# ---------------------------------------------------------------------------

class BaseConnector(ABC):
    name: str

    def load_config(self, vault: Path) -> dict:
        cfg_path = vault / ".icontext" / "connectors.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get(self.name, {})
        return {}

    def save_config(self, vault: Path, config: dict) -> None:
        cfg_path = vault / ".icontext" / "connectors.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        all_cfg = {}
        if cfg_path.exists():
            all_cfg = json.loads(cfg_path.read_text())
        all_cfg[self.name] = config
        cfg_path.write_text(json.dumps(all_cfg, indent=2))

    def write_profile(self, vault: Path, rel_path: str, content: str) -> None:
        out = vault / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        # git commit
        try:
            subprocess.run(["git", "-C", str(vault), "add", rel_path], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(vault), "commit", "-m", f"icontext: sync {self.name} {datetime.now(UTC).strftime('%Y-%m-%d')}"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError:
            pass  # nothing to commit or git not configured

    def gemini_synthesize(self, prompt: str) -> str:
        """Call ai-sidecar gemini for synthesis."""
        # Check ai-sidecar is available
        sidecar_check = subprocess.run(["which", "ai-sidecar"], capture_output=True)
        if sidecar_check.returncode != 0:
            raise RuntimeError(
                "ai-sidecar not found. Install it first:\n"
                "  See: https://github.com/floomhq/icontext#requirements"
            )

        _print(_info("synthesizing with Gemini...") + "          ")
        if sys.stdout.isatty():
            print(f"\033[A\r  {_c(C.CYAN, '→')} synthesizing with Gemini...", end="", flush=True)
        result = subprocess.run(
            ["ai-sidecar", "gemini", "--model", "gemini-2.5-flash", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            if sys.stdout.isatty():
                print()
            raise RuntimeError(f"Gemini synthesis failed: {result.stderr[:500]}")
        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")
        return result.stdout.strip()

    @abstractmethod
    def connect(self, vault: Path) -> None:
        """Interactive setup: collect credentials and save config."""

    @abstractmethod
    def sync(self, vault: Path) -> str:
        """Run sync, write profile file, return summary string."""

    @abstractmethod
    def status(self, vault: Path) -> dict:
        """Return dict with: connected (bool), last_sync (str|None), summary (str)."""
