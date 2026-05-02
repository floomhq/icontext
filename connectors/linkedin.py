"""LinkedIn data export connector for icontext."""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .base import BaseConnector

_SYNTHESIS_PROMPT = """Build a structured professional profile from this LinkedIn data export for use by an AI assistant (Claude Code). The AI will use this to understand the person's professional background, network, and positioning.

## Professional Summary
Name, current role, headline. 2-3 sentences on career trajectory.

## Work History
Table: Company | Role | Duration | Key Notes
Last 5-7 positions only.

## Education
Table: School | Degree | Field | Years

## Key Skills
Top 10-15 skills as a comma-separated list.

## Network Highlights
From connections data: top companies represented, notable connections (if any patterns stand out), approximate network size and composition.

## Positioning
How would this person introduce themselves professionally? 1 paragraph.

---
DATA:
{summary}"""


def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """Read a CSV from the ZIP, return list of row dicts. Returns [] if not found."""
    # Try exact name first, then case-insensitive search
    names_in_zip = zf.namelist()
    target = None
    for n in names_in_zip:
        if n.lower().endswith(name.lower()) or n.lower().endswith(name.lower().replace(".csv", "") + ".csv"):
            target = n
            break
    if target is None:
        return []
    try:
        raw = zf.read(target).decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(raw))
        return [row for row in reader]
    except Exception:
        return []


def _is_linkedin_export(zf: zipfile.ZipFile) -> bool:
    """Quick sanity check that this looks like a LinkedIn export."""
    names = {n.lower() for n in zf.namelist()}
    indicators = {"profile.csv", "connections.csv", "positions.csv", "education.csv", "skills.csv"}
    return bool(names & indicators)


def _build_summary(zf: zipfile.ZipFile) -> str:
    lines: list[str] = []

    # Profile
    profile_rows = _read_csv_from_zip(zf, "Profile.csv")
    if profile_rows:
        p = profile_rows[0]
        lines.append("== PROFILE ==")
        for key in ("First Name", "Last Name", "Headline", "Summary", "Industry", "Current Position"):
            val = p.get(key, "").strip()
            if val:
                lines.append(f"  {key}: {val}")
        lines.append("")

    # Positions
    position_rows = _read_csv_from_zip(zf, "Positions.csv")
    if position_rows:
        lines.append("== WORK HISTORY (most recent first) ==")
        for row in position_rows[:10]:
            company = row.get("Company Name", row.get("Company", "")).strip()
            title = row.get("Title", "").strip()
            started = row.get("Started On", "").strip()
            finished = row.get("Finished On", "").strip() or "present"
            description = row.get("Description", "").strip()
            if company or title:
                entry = f"  {title} @ {company} ({started} - {finished})"
                if description:
                    entry += f"\n    {description[:200]}"
                lines.append(entry)
        lines.append("")

    # Education
    education_rows = _read_csv_from_zip(zf, "Education.csv")
    if education_rows:
        lines.append("== EDUCATION ==")
        for row in education_rows:
            school = row.get("School Name", row.get("School", "")).strip()
            degree = row.get("Degree Name", row.get("Degree", "")).strip()
            field = row.get("Field Of Study", "").strip()
            started = row.get("Start Date", row.get("Started On", "")).strip()
            finished = row.get("End Date", row.get("Finished On", "")).strip()
            if school:
                lines.append(f"  {school} | {degree} {field} ({started}-{finished})")
        lines.append("")

    # Skills
    skill_rows = _read_csv_from_zip(zf, "Skills.csv")
    if skill_rows:
        skill_names = [r.get("Name", r.get("Skill", "")).strip() for r in skill_rows if r.get("Name", r.get("Skill", ""))]
        if skill_names:
            lines.append("== SKILLS ==")
            lines.append("  " + ", ".join(skill_names[:30]))
            lines.append("")

    # Connections
    connection_rows = _read_csv_from_zip(zf, "Connections.csv")
    if connection_rows:
        lines.append(f"== CONNECTIONS (total: {len(connection_rows)}) ==")
        from collections import Counter
        company_counter: Counter = Counter()
        for row in connection_rows:
            company = row.get("Company", "").strip()
            if company:
                company_counter[company] += 1
        top_companies = company_counter.most_common(20)
        lines.append("  Top companies in network:")
        for company, count in top_companies:
            lines.append(f"    {company}: {count} connections")
        # Sample of connections
        lines.append(f"  Sample connections (first 30):")
        for row in connection_rows[:30]:
            first = row.get("First Name", "").strip()
            last = row.get("Last Name", "").strip()
            title = row.get("Position", row.get("Title", "")).strip()
            company = row.get("Company", "").strip()
            if first or last:
                lines.append(f"    {first} {last} — {title} @ {company}")
        lines.append("")

    # Recommendations received
    rec_rows = _read_csv_from_zip(zf, "Recommendations_Received.csv")
    if rec_rows:
        lines.append(f"== RECOMMENDATIONS RECEIVED ({len(rec_rows)}) ==")
        for row in rec_rows[:5]:
            sender = row.get("Recommender", row.get("First Name", "")).strip()
            text = row.get("Text", row.get("Recommendation Text", "")).strip()
            if text:
                lines.append(f"  From {sender}: {text[:200]}")
        lines.append("")

    return "\n".join(lines)


class LinkedInConnector(BaseConnector):
    name = "linkedin"

    def connect(self, vault: Path) -> None:
        print("LinkedIn data export connector setup")
        print("Request your data export at: LinkedIn → Settings → Data privacy → Get a copy of your data")
        print("Download the ZIP and provide the path below.")
        print()

        cfg = self.load_config(vault)

        while True:
            raw_path = input("Path to LinkedIn data export ZIP: ").strip()
            if not raw_path:
                print("Path is required.")
                continue

            # Expand ~ and resolve
            export_path = Path(raw_path).expanduser().resolve()
            if not export_path.exists():
                print(f"File not found: {export_path}")
                retry = input("Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue

            if not export_path.suffix.lower() == ".zip":
                print("File does not appear to be a ZIP archive.")
                retry = input("Try anyway? [y/N]: ").strip().lower()
                if retry != "y":
                    break

            try:
                with zipfile.ZipFile(export_path) as zf:
                    if not _is_linkedin_export(zf):
                        print("This ZIP does not look like a LinkedIn export (missing Profile.csv, Connections.csv, etc.).")
                        print("Files found:", ", ".join(zf.namelist()[:10]))
                        retry = input("Use it anyway? [y/N]: ").strip().lower()
                        if retry != "y":
                            break
            except zipfile.BadZipFile:
                print("File is not a valid ZIP archive.")
                retry = input("Try again? [y/N]: ").strip().lower()
                if retry != "y":
                    break
                continue

            cfg["export_path"] = str(export_path)
            self.save_config(vault, cfg)
            print(f"Saved LinkedIn export path: {export_path}")
            break

    def sync(self, vault: Path) -> str:
        cfg = self.load_config(vault)
        export_path_str = cfg.get("export_path")
        if not export_path_str:
            raise RuntimeError("No LinkedIn export configured. Run: icontext connect linkedin")

        export_path = Path(export_path_str)
        if not export_path.exists():
            raise RuntimeError(f"LinkedIn export ZIP not found: {export_path}")

        print(f"Reading LinkedIn export: {export_path}")
        with zipfile.ZipFile(export_path) as zf:
            summary = _build_summary(zf)

        if not summary.strip():
            raise RuntimeError("No data found in LinkedIn export ZIP.")

        # Trim for Gemini
        if len(summary) > 8000:
            summary = summary[:8000] + "\n[truncated]"

        prompt = _SYNTHESIS_PROMPT.format(summary=summary)
        print("Synthesizing profile with Gemini...")
        gemini_output = self.gemini_synthesize(prompt)

        profile = (
            f"---\n"
            f"source: LinkedIn data export\n"
            f"export_file: {export_path.name}\n"
            f"generated: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
            f"refresh: icontext sync linkedin\n"
            f"---\n\n"
            f"{gemini_output}\n"
        )

        self.write_profile(vault, "internal/profile/linkedin.md", profile)

        cfg["last_sync"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save_config(vault, cfg)

        return f"LinkedIn sync complete from {export_path.name}"

    def status(self, vault: Path) -> dict:
        cfg = self.load_config(vault)
        export_path = cfg.get("export_path")
        connected = export_path is not None
        last_sync = cfg.get("last_sync")
        if export_path:
            summary = f"export: {Path(export_path).name}"
        else:
            summary = "not configured"
        return {"connected": connected, "last_sync": last_sync, "summary": summary}
