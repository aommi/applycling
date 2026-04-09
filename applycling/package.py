"""Package Assembler.

Takes a tailored resume + fit summary + job metadata and produces a per-job
folder with everything a recruiter (or a future autopilot agent) needs to
submit the application.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from . import render
from .tracker import Job

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def folder_name(company: str, title: str, date: Optional[str] = None) -> str:
    """Return the canonical {company}-{title}-{date} folder name."""
    if date is None:
        date = dt.date.today().isoformat()
    return f"{_slugify(company)}-{_slugify(title)}-{date}"


def assemble(
    job: Job,
    tailored_markdown: str,
    fit_summary: str,
    output_root: Optional[Path] = None,
) -> Path:
    """Build the application package folder for a job.

    Writes:
      - resume.md       (canonical Markdown source)
      - resume.html     (rendered HTML for review)
      - resume.pdf      (rendered via headless Chromium so it matches HTML)
      - fit_summary.md  (the LLM's fit summary)
      - job.json        (machine-readable manifest)

    Returns the absolute path to the folder.
    """
    base = (output_root or OUTPUT_DIR).resolve()
    base.mkdir(parents=True, exist_ok=True)

    name = folder_name(job.company, job.title, job.date_added.split("T")[0] if job.date_added else None)
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    # Resume artefacts (md, html, pdf) — the WYSIWYG triple.
    render.render_resume(
        tailored_markdown,
        folder,
        title=f"{job.title} — {job.company}",
    )

    # Fit summary as its own file.
    (folder / "fit_summary.md").write_text(
        f"# Fit summary — {job.title} @ {job.company}\n\n{fit_summary}\n",
        encoding="utf-8",
    )

    # Manifest. Useful for the autopilot agent later, and for humans now.
    manifest = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "status": job.status,
        "source_url": job.source_url,
        "application_url": job.application_url,
        "date_added": job.date_added,
        "date_updated": job.date_updated,
        "files": {
            "resume_md": "resume.md",
            "resume_html": "resume.html",
            "resume_pdf": "resume.pdf",
            "fit_summary": "fit_summary.md",
        },
    }
    (folder / "job.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return folder
