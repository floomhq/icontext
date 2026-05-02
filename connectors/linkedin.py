"""LinkedIn PDF connector for icontext."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .base import BaseConnector

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
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout

    # Fallback: try pypdf if available
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        raise RuntimeError(
            "Cannot read PDF. Install pdftotext: brew install poppler\n"
            "Or: pip install pypdf"
        )


class LinkedInConnector(BaseConnector):
    name = "linkedin"

    def connect(self, vault: Path, pdf_path: str | None = None) -> None:
        if pdf_path is None:
            print("icontext: Connect LinkedIn")
            print("─────────────────────────────────────────────")
            print("Save your LinkedIn profile as a PDF:")
            print()
            print("  1. Go to: linkedin.com/in/your-username")
            print("  2. Click the \"More\" button below your name")
            print("  3. Click \"Save to PDF\"")
            print("  4. The PDF downloads to your Downloads folder")
            print()
            raw_path = input("Path to your LinkedIn PDF [~/Downloads/Profile.pdf]: ").strip()
            if not raw_path:
                raw_path = "~/Downloads/Profile.pdf"
        else:
            raw_path = pdf_path

        export_path = Path(raw_path).expanduser().resolve()

        cfg = self.load_config(vault)

        if not export_path.exists():
            print(f"File not found: {export_path}")
            print("Run 'icontext connect linkedin' again once the file is downloaded.")
            return

        if export_path.suffix.lower() != ".pdf":
            print(f"Warning: file does not appear to be a PDF: {export_path.name}")

        cfg["pdf_path"] = str(export_path)
        self.save_config(vault, cfg)
        print(f"icontext: LinkedIn PDF configured: {export_path}")

    def sync(self, vault: Path) -> str:
        cfg = self.load_config(vault)
        pdf_path_str = cfg.get("pdf_path")
        if not pdf_path_str:
            raise RuntimeError("No LinkedIn PDF configured. Run: icontext connect linkedin")

        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            raise RuntimeError(f"LinkedIn PDF not found: {pdf_path}")

        print(f"Reading LinkedIn PDF: {pdf_path}")
        text = _read_pdf_text(pdf_path)

        if not text.strip():
            raise RuntimeError("No text extracted from LinkedIn PDF.")

        # Trim for Gemini
        if len(text) > 8000:
            text = text[:8000] + "\n[truncated]"

        prompt = _SYNTHESIS_PROMPT.format(text=text)
        print("Synthesizing profile with Gemini...")
        gemini_output = self.gemini_synthesize(prompt)

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
