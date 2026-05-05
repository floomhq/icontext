"""Base connector interface for fbrain data sources."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
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


def _print(msg: str = "", **kwargs) -> None:
    if not sys.stdout.isatty():
        print(_strip_ansi(msg), **kwargs)
    else:
        print(msg, **kwargs)


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
        """Write a file. Use commit_profiles() once at the end of sync() to commit."""
        out = vault / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)

    def commit_profiles(self, vault: Path) -> None:
        """Stage and commit all fbrain changes in a single atomic commit."""
        try:
            subprocess.run(
                ["git", "-C", str(vault), "add", "-A"],
                check=True, capture_output=True,
            )
            result = subprocess.run(
                ["git", "-C", str(vault), "commit", "-m",
                 f"fbrain: sync {self.name} {datetime.now(UTC).strftime('%Y-%m-%d')}"],
                capture_output=True, text=True,
            )
            # Exit 1 with "nothing to commit" is acceptable; surface other errors.
            if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
                _print(_warn(f"git commit failed: {result.stderr.strip() or result.stdout.strip()}"))
        except subprocess.CalledProcessError as e:
            _print(_warn(f"git stage failed: {e.stderr.decode() if e.stderr else e}"))
        except FileNotFoundError:
            _print(_warn("git not installed — skipping commit"))

    def _gemini_configure(self):
        """Common setup. Returns the genai module."""
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.generativeai.*")

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set — Gemini is required to generate your profile.\n"
                "\n"
                "  1. Get a free key (no credit card): https://aistudio.google.com/apikey\n"
                "  2. Export it in your current shell:\n"
                "       export GEMINI_API_KEY=your_key_here\n"
                "  3. Make it permanent — add that line to ~/.zshrc or ~/.bashrc,\n"
                "     then open a new terminal and re-run: fbrain sync"
            )
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError(
                "google-generativeai is not installed.\n"
                "  Run: pip install google-generativeai\n"
                "  Then re-run: fbrain sync"
            )
        genai.configure(api_key=api_key)
        return genai

    def gemini_synthesize(self, prompt: str) -> str:
        """Free-form Gemini call. Used for shareable card and legacy paths."""
        genai = self._gemini_configure()
        print("    synthesizing with Gemini...", end="", flush=True)
        model_name = os.environ.get("FBRAIN_GEMINI_MODEL") or os.environ.get("ICONTEXT_GEMINI_MODEL", "gemini-2.5-flash-lite")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        print(" ✓")
        # Some safety blocks raise on .text; guard.
        try:
            text = response.text
        except Exception as e:
            raise RuntimeError(f"Gemini returned no usable text (likely safety-blocked): {e}")
        return (text or "").strip()

    def gemini_json(self, prompt: str, schema: dict) -> dict:
        """JSON-mode Gemini call with a typed schema. Returns parsed dict."""
        genai = self._gemini_configure()
        model_name = os.environ.get("FBRAIN_GEMINI_MODEL") or os.environ.get("ICONTEXT_GEMINI_MODEL", "gemini-2.5-flash-lite")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        try:
            text = response.text
        except Exception as e:
            raise RuntimeError(f"Gemini returned no usable text (likely safety-blocked): {e}")
        if not text or not text.strip():
            raise RuntimeError("Gemini returned an empty response.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Gemini returned invalid JSON: {e}\nFirst 200 chars: {text[:200]}")

    def gemini_call_with_retry(self, prompt: str, schema: dict | None = None,
                                max_retries: int = 2) -> str | dict:
        """Wrap gemini_synthesize / gemini_json with exponential-backoff retry."""
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                if schema is not None:
                    return self.gemini_json(prompt, schema)
                return self.gemini_synthesize(prompt)
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Gemini failed after {max_retries + 1} attempts: {last_err}")

    @abstractmethod
    def connect(self, vault: Path) -> None:
        """Interactive setup: collect credentials and save config."""

    @abstractmethod
    def sync(self, vault: Path) -> str:
        """Run sync, write profile file, return summary string."""

    @abstractmethod
    def status(self, vault: Path) -> dict:
        """Return dict with: connected (bool), last_sync (str|None), summary (str)."""
