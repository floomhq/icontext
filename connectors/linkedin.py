"""LinkedIn PDF connector for icontext."""
from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .base import BaseConnector, C, _c, _ok, _info, _warn, _err, _hr, _print

_SYNTHESIS_PROMPT = """Build a structured professional profile from this LinkedIn PDF export for use by an AI assistant (Claude Code). The AI will use this to understand the person's professional background, skills, and positioning.

## Professional Summary
Name, current role, headline. 2-3 sentences on career trajectory.

## Work History
Table: Company | Role | Duration | Key Notes
Last 5-7 positions only.

## Education
Table: School | Degree | Field | Years

## Key Skills
Top 10-15 skills as a comma-separated list.

## Network / Recommendations
Any notable recommendations or network signals visible in the PDF.

## Positioning
How would this person introduce themselves professionally? 1 paragraph.

---
DATA:
{text}"""


def _read_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Tries pdftotext first, then pypdf."""
    # Try pdftotext first (brew install poppler / apt install poppler-utils)
    pdftotext_result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if pdftotext_result.returncode == 0 and pdftotext_result.stdout.strip():
        return pdftotext_result.stdout

    # Fallback: try pypdf if available
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
        raise RuntimeError(
            f"PDF appears to be empty or image-only: {pdf_path.name}\n"
            "Make sure you saved it via LinkedIn → More → Save to PDF (not a browser print)."
        )
    except ImportError:
        raise RuntimeError(
            "Cannot read PDF — no PDF reader found.\n"
            "\n"
            "Fix (pick one):\n"
            "  Option A: brew install poppler   (installs pdftotext)\n"
            "  Option B: pip install pypdf\n"
            "\n"
            "After installing, re-run: icontext connect linkedin"
        )


class LinkedInConnector(BaseConnector):
    name = "linkedin"

    def connect(self, vault: Path, pdf_path: str | None = None) -> None:
        _print("")
        _print(_hr())
        _print(f"    {_c(C.BOLD, 'icontext · connect linkedin')}")
        _print(_hr())

        if pdf_path is None:
            _print("")
            _print("  Save your LinkedIn profile as a PDF:")
            _print("")
            _print(_info("Go to: linkedin.com/in/your-username"))
            _print(_info("Click the \"More\" button below your name"))
            _print(_info("Click \"Save to PDF\""))
            _print(_info("The PDF downloads to ~/Downloads/ (usually Profile.pdf)"))
            _print("")
            raw_path = input("  Path to your LinkedIn PDF [~/Downloads/Profile.pdf]: ").strip()
            if not raw_path:
                raw_path = "~/Downloads/Profile.pdf"
        else:
            raw_path = pdf_path

        export_path = Path(raw_path).expanduser().resolve()

        cfg = self.load_config(vault)

        if not export_path.exists():
            # Try to help the user find their file
            downloads = Path("~/Downloads").expanduser()
            pdf_candidates = sorted(downloads.glob("*.pdf")) if downloads.is_dir() else []
            _print(_err(f"File not found: {export_path}"))
            if pdf_candidates:
                _print("")
                _print("  PDFs in ~/Downloads:")
                for p in pdf_candidates[-5:]:
                    _print(_info(p.name))
                _print("")
                _print(_info(f"Re-run: icontext connect linkedin --pdf ~/Downloads/{pdf_candidates[-1].name}"))
            else:
                _print("")
                _print(_warn("No PDFs found in ~/Downloads. Download your LinkedIn PDF first:"))
                _print(_info("linkedin.com/in/your-username → More → Save to PDF"))
                _print("")
                _print(_info("Then re-run: icontext connect linkedin"))
            return

        if export_path.suffix.lower() != ".pdf":
            _print(_warn(f"file does not appear to be a PDF: {export_path.name}"))

        _print(_ok(f"PDF found: {export_path.name}"))

        cfg["pdf_path"] = str(export_path)
        self.save_config(vault, cfg)
        _print(_ok("LinkedIn connected"))
        _print(_hr())
        _print(_info("Run: icontext sync"))

    def sync(self, vault: Path) -> str:
        cfg = self.load_config(vault)
        pdf_path_str = cfg.get("pdf_path")
        if not pdf_path_str:
            raise RuntimeError("No LinkedIn PDF configured. Run: icontext connect linkedin")

        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            raise RuntimeError(f"LinkedIn PDF not found: {pdf_path}")

        label_width = 36

        # Step 1: read PDF
        read_label = "reading Profile.pdf..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {read_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(read_label))
        text = _read_pdf_text(pdf_path)
        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")
        else:
            _print(_ok("PDF read"))

        if not text.strip():
            raise RuntimeError("No text extracted from LinkedIn PDF.")

        # Trim for Gemini
        if len(text) > 8000:
            text = text[:8000] + "\n[truncated]"

        prompt = _SYNTHESIS_PROMPT.format(text=text)

        # Step 2: synthesize
        synth_label = "synthesizing with Gemini..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {synth_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(synth_label))

        sidecar_check = subprocess.run(["which", "ai-sidecar"], capture_output=True)
        if sidecar_check.returncode != 0:
            if sys.stdout.isatty():
                print(f" {_c(C.RED, '✗')}")
            raise RuntimeError(
                "ai-sidecar not found. Install it first:\n"
                "  See: https://github.com/floomhq/icontext#requirements"
            )
        result = subprocess.run(
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
        else:
            _print(_ok("synthesized"))

        # Step 3: write profile
        write_label = "writing profile..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {write_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(write_label))

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        profile = (
            f"---\n"
            f"source: LinkedIn PDF\n"
            f"pdf_file: {pdf_path.name}\n"
            f"generated: {today}\n"
            f"refresh: icontext sync linkedin\n"
            f"---\n\n"
            f"{gemini_output}\n"
        )

        self.write_profile(vault, "internal/profile/linkedin.md", profile)

        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")
        else:
            _print(_ok("profile written"))

        cfg["last_sync"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save_config(vault, cfg)

        return f"LinkedIn sync complete from {pdf_path.name}"

    def status(self, vault: Path) -> dict:
        cfg = self.load_config(vault)
        pdf_path = cfg.get("pdf_path")
        connected = pdf_path is not None
        last_sync = cfg.get("last_sync")
        if pdf_path:
            summary = f"pdf: {Path(pdf_path).name}"
        else:
            summary = "not configured"
        return {"connected": connected, "last_sync": last_sync, "summary": summary}
