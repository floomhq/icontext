"""LinkedIn PDF connector for icontext."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .base import BaseConnector, C, _c, _ok, _info, _warn, _err, _hr, _print


_LINKEDIN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "current_role": {"type": "string"},
        "current_company": {"type": "string"},
        "work_history": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "duration": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["company", "role"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": "string"},
                    "field": {"type": "string"},
                    "years": {"type": "string"},
                },
                "required": ["school"],
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "positioning": {"type": "string"},
    },
    "required": ["name", "headline", "summary", "work_history", "education", "skills", "positioning"],
}


def _linkedin_prompt(text: str) -> str:
    return (
        "Extract a structured professional profile from this LinkedIn PDF text. "
        "Output MUST match the JSON schema. Be specific. Use real names from the text. "
        "Do not invent information that is not present.\n"
        "\n"
        "RULES:\n"
        "- name: the person's full name as printed.\n"
        "- headline: their LinkedIn headline (one line under their name).\n"
        "- summary: 2-3 sentences on career trajectory, in plain second-person voice ('You ...').\n"
        "- work_history: last 5-7 positions, most recent first.\n"
        "- skills: top 10-15 skills as a flat list.\n"
        "- positioning: 1 paragraph, plain voice, no buzzwords like 'leveraging', "
        "'pioneering', 'driving innovation'.\n"
        "\n"
        "PDF TEXT:\n"
        f"{text}\n"
    )


def _read_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Tries pdftotext first, then pypdf."""
    pdftotext_result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if pdftotext_result.returncode == 0 and pdftotext_result.stdout.strip():
        return pdftotext_result.stdout

    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
        raise RuntimeError(
            f"PDF appears to be empty or image-only: {pdf_path.name}\n"
            "  LinkedIn PDFs saved via browser Print→Save are image-only and cannot be parsed.\n"
            "  Use the official export instead: linkedin.com/in/you → More → Save to PDF\n"
            "  Then re-run: icontext connect linkedin --pdf ~/Downloads/Profile.pdf"
        )
    except ImportError:
        raise RuntimeError(
            f"Cannot read {pdf_path.name} — no PDF reader available.\n"
            "\n"
            "  Install one (pick either):\n"
            "    brew install poppler        # installs pdftotext (recommended)\n"
            "    pip install pypdf           # pure-Python fallback\n"
            "\n"
            "  Then re-run: icontext connect linkedin --pdf {pdf_path}"
        )


def _render_linkedin_md(profile: dict, today: str, pdf_name: str) -> str:
    lines: list[str] = [
        "---",
        "source: LinkedIn PDF",
        f"pdf_file: {pdf_name}",
        f"generated: {today}",
        "refresh: icontext sync linkedin",
        "---",
        "",
        "## Professional Summary",
        "",
        f"**{profile.get('name', '')}** — {profile.get('headline', '')}",
        "",
        profile.get("summary", "").strip() or "_(no summary)_",
        "",
        "## Work History",
        "",
    ]
    work = profile.get("work_history") or []
    if work:
        lines.append("| Company | Role | Duration | Notes |")
        lines.append("|---------|------|----------|-------|")
        for w in work:
            lines.append(
                f"| {w.get('company','')} | {w.get('role','')} "
                f"| {w.get('duration','')} | {w.get('notes','')} |"
            )
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Education")
    lines.append("")
    edu = profile.get("education") or []
    if edu:
        lines.append("| School | Degree | Field | Years |")
        lines.append("|--------|--------|-------|-------|")
        for e in edu:
            lines.append(
                f"| {e.get('school','')} | {e.get('degree','')} "
                f"| {e.get('field','')} | {e.get('years','')} |"
            )
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Key Skills")
    lines.append("")
    skills = profile.get("skills") or []
    lines.append(", ".join(skills) if skills else "_(none)_")
    lines.append("")

    lines.append("## Positioning")
    lines.append("")
    lines.append(profile.get("positioning", "").strip() or "_(none)_")
    lines.append("")

    return "\n".join(lines) + "\n"


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

        _print(_info("testing PDF..."), end="", flush=True)
        try:
            text = _read_pdf_text(export_path)
            if len(text.strip()) < 100:
                raise RuntimeError(
                    f"{export_path.name} is too short to be a valid LinkedIn export "
                    f"({len(text.strip())} chars — expected at least 100).\n"
                    "  Make sure you used LinkedIn → More → Save to PDF, not a browser print.\n"
                    f"  Then re-run: icontext connect linkedin --pdf {export_path}"
                )
            _print(f" {C.GREEN}✓{C.RESET} ({len(text)} chars)")
        except RuntimeError:
            _print(f" {C.RED}✗{C.RESET}")
            raise

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
            raise RuntimeError(
                f"LinkedIn PDF no longer exists at: {pdf_path}\n"
                "  Re-run: icontext connect linkedin --pdf /path/to/Profile.pdf"
            )

        label_width = 36

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
            raise RuntimeError(
                f"No text could be extracted from {pdf_path.name}.\n"
                "  The file may be image-only (browser-printed PDF).\n"
                "  Use the official export: linkedin.com/in/you → More → Save to PDF\n"
                f"  Then re-run: icontext connect linkedin --pdf {pdf_path}"
            )

        # Soft cap; the JSON-schema call handles structure, so we don't need to
        # truncate aggressively. Stay well under context limits.
        if len(text) > 16000:
            text = text[:16000] + "\n[truncated]"

        prompt = _linkedin_prompt(text)
        result = self.gemini_call_with_retry(prompt, schema=_LINKEDIN_SCHEMA)
        if not isinstance(result, dict):
            raise RuntimeError("LinkedIn synthesis did not return structured output.")

        # Validate required fields are non-empty.
        missing = [k for k in ("name", "summary", "work_history", "education")
                   if not result.get(k)]
        if missing:
            raise RuntimeError(
                f"LinkedIn synthesis missing required fields: {', '.join(missing)}.\n"
                "  Re-run: icontext sync linkedin"
            )

        write_label = "writing profile..."
        if sys.stdout.isatty():
            print(f"  {_c(C.CYAN, '→')} {write_label:<{label_width}}", end="", flush=True)
        else:
            _print(_info(write_label))

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        md = _render_linkedin_md(result, today, pdf_path.name)
        self.write_profile(vault, "internal/profile/linkedin.md", md)

        if sys.stdout.isatty():
            print(f" {_c(C.GREEN, '✓')}")
        else:
            _print(_ok("profile written"))

        cfg["last_sync"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save_config(vault, cfg)
        self.commit_profiles(vault)

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
