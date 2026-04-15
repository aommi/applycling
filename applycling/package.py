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


def folder_name(company: str, title: str, date: Optional[str] = None, model: Optional[str] = None, job_id: Optional[str] = None) -> str:
    """Return the canonical {job_id}-{company}-{title}-{date}[-{model}] folder name."""
    if date is None:
        date = dt.date.today().isoformat()
    prefix = f"{job_id}-" if job_id else ""
    base = f"{prefix}{_slugify(company)}-{_slugify(title)}-{date}"
    if model:
        return f"{base}-{_slugify(model)}"
    return base


def assemble(
    job: Job,
    tailored_markdown: str,
    fit_summary: str,
    output_root: Optional[Path] = None,
    strategy: Optional[str] = None,
    company_context: Optional[str] = None,
    positioning_brief: Optional[str] = None,
    cover_letter: Optional[str] = None,
    email_inmail: Optional[str] = None,
    job_description: Optional[str] = None,
    generate_docx: bool = False,
    run_log: Optional[dict] = None,
    model: Optional[str] = None,
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

    name = folder_name(job.company, job.title, job.date_added.split("T")[0] if job.date_added else None, model=model, job_id=job.id or None)
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    # Resume artefacts (md, html, pdf) — the WYSIWYG triple.
    render.render_resume(
        tailored_markdown,
        folder,
        title=f"{job.title} — {job.company}",
    )
    if generate_docx:
        render.markdown_to_docx(tailored_markdown, folder / "resume.docx")

    # Fit summary as its own file.
    (folder / "fit_summary.md").write_text(
        f"# Fit summary — {job.title} @ {job.company}\n\n{fit_summary}\n",
        encoding="utf-8",
    )

    if strategy:
        (folder / "strategy.md").write_text(
            f"# Role strategy — {job.title} @ {job.company}\n\n{strategy}\n",
            encoding="utf-8",
        )

    if company_context:
        (folder / "company_context.md").write_text(
            f"# Company context — {job.company}\n\n{company_context}\n",
            encoding="utf-8",
        )

    if positioning_brief:
        (folder / "positioning_brief.md").write_text(
            f"# Positioning brief — {job.title} @ {job.company}\n\n{positioning_brief}\n",
            encoding="utf-8",
        )

    if cover_letter:
        cl_md = f"# Cover Letter — {job.title} @ {job.company}\n\n{cover_letter}\n"
        (folder / "cover_letter.md").write_text(cl_md, encoding="utf-8")
        cl_html = render.markdown_to_html(cl_md, title=f"Cover Letter — {job.title}")
        cl_html_path = folder / "cover_letter.html"
        cl_html_path.write_text(cl_html, encoding="utf-8")
        render.html_to_pdf(cl_html_path, folder / "cover_letter.pdf")
        if generate_docx:
            render.markdown_to_docx(cl_md, folder / "cover_letter.docx")

    if email_inmail:
        (folder / "email_inmail.md").write_text(
            f"# Outreach — {job.title} @ {job.company}\n\n{email_inmail}\n",
            encoding="utf-8",
        )

    if job_description:
        (folder / "job_description.md").write_text(
            f"# Job Description — {job.title} @ {job.company}\n\n{job_description}\n",
            encoding="utf-8",
        )

    # Create intel/ subfolder for interview prep notes (populated later via refine --intel).
    (folder / "intel").mkdir(exist_ok=True)

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

    # Run log — enumerate actual files written with sizes.
    if run_log is not None:
        run_log["package_folder"] = str(folder)
        files_inventory = {}
        for f in sorted(folder.iterdir()):
            if f.name == "run_log.json":
                continue
            files_inventory[f.name] = {
                "bytes": f.stat().st_size,
                "generated": True,
            }
        run_log["files"] = files_inventory
        (folder / "run_log.json").write_text(
            json.dumps(run_log, indent=2), encoding="utf-8"
        )

    return folder
