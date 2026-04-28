"""Index existing output directories into the job tracker.

Scans a user's output directory for previously generated application packages
and imports them as job records. Designed to make the workbench useful
immediately after installation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .tracker import STATUSES, Job, TrackerError, get_store

# Known artifact filenames that signal a valid package folder.
REQUIRED_ONE_OF = frozenset({
    "resume.pdf",
    "cover_letter.pdf",
    "resume.md",
    "job_description.md",
})

# Files to register as artifacts when found.
ARTIFACT_NAMES = [
    "resume.pdf",
    "resume.md",
    "resume.html",
    "resume.docx",
    "cover_letter.pdf",
    "cover_letter.md",
    "cover_letter.html",
    "cover_letter.docx",
    "job_description.md",
    "fit_summary.md",
    "positioning_brief.md",
    "email_inmail.md",
    "strategy.md",
    "company_context.md",
    "run_log.json",
]


def _parse_job_description_md(path: Path) -> dict[str, str]:
    """Parse job_description.md to extract title and company.

    Expected format: ``# Job Description — Title @ Company``
    Falls back to inferring from the folder name.
    """
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result

    # Try to parse the first heading: "# Job Description — Title @ Company"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            heading = line[2:].strip()
            # Remove "Job Description — " or "Job Description - " prefix
            heading = re.sub(r'^Job\s+Description\s*(?:—|–|-)\s*', '', heading)
            # Split on " @ " or " at " for company
            parts = re.split(r'\s+@\s+|\s+at\s+', heading, maxsplit=1)
            result["title"] = parts[0].strip()
            if len(parts) > 1:
                result["company"] = parts[1].strip()
            break

    return result


def _scan_folder(folder: Path) -> dict[str, Any] | None:
    """Scan a single output folder and return job metadata + artifacts.

    Returns None if the folder doesn't look like a valid package.
    """
    if not folder.is_dir():
        return None
    if folder.name.startswith("."):
        return None

    # List all files in the folder (non-recursive).
    try:
        files = [f for f in folder.iterdir() if f.is_file()]
    except OSError:
        return None

    file_names = {f.name for f in files}

    # Must have at least one required artifact.
    if not (file_names & REQUIRED_ONE_OF):
        return None

    # --- Extract metadata ---
    title = ""
    company = ""
    source_url = ""

    # Best source: job.json
    job_json_path = folder / "job.json"
    if job_json_path.exists():
        try:
            meta = json.loads(job_json_path.read_text(encoding="utf-8"))
            title = meta.get("title", "").strip()
            company = meta.get("company", "").strip()
            source_url = meta.get("source_url", "").strip()
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: parse job_description.md
    if (not title or not company) and "job_description.md" in file_names:
        parsed = _parse_job_description_md(folder / "job_description.md")
        if not title:
            title = parsed.get("title", "")
        if not company:
            company = parsed.get("company", "")

    # Fallback: infer from folder name (e.g., "job_007-microsoft-senior-product-manager-2026-04-27")
    if not title or not company:
        parts = folder.name.split("-")
        # Skip job_NNN prefix
        start = 1 if parts and re.match(r'^job_\d+$', parts[0]) else 0

        # Find the date suffix: three consecutive parts YYYY, MM, DD
        date_start = None
        for i in range(len(parts) - 2):
            if (re.match(r'^\d{4}$', parts[i]) and
                    re.match(r'^\d{2}$', parts[i+1]) and
                    re.match(r'^\d{2}$', parts[i+2])):
                date_start = i
                break

        # Content between prefix and date (or model name)
        end = date_start if date_start is not None else len(parts)
        # Also stop at model names (claude-sonnet-4-6 etc.)
        for i in range(start, end):
            if parts[i].lower() in ("claude", "sonnet", "haiku", "opus", "gpt", "gemini"):
                end = i
                break

        content = parts[start:end]
        if content:
            # Heuristic: first word = company, rest = title
            if not company:
                company = content[0].title()
            if not title and len(content) > 1:
                title = " ".join(content[1:]).title()

    if not title:
        title = folder.name

    # Source URL: check source_url.txt
    source_url_path = folder / "source_url.txt"
    if source_url_path.exists():
        try:
            source_url = source_url_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    if not source_url:
        source_url = f"file://imported/{folder.name}"

    # Collect artifact paths.
    artifacts: dict[str, str] = {}
    for art_name in ARTIFACT_NAMES:
        if art_name in file_names:
            artifacts[art_name] = str(folder / art_name)

    return {
        "title": title,
        "company": company or "Unknown",
        "source_url": source_url,
        "package_folder": str(folder),
        "artifacts": artifacts,
    }


def index_output_dir(output_root: str = "output") -> dict[str, Any]:
    """Scan *output_root* for generated packages and import as job records.

    Parameters
    ----------
    output_root:
        Path to the output directory. Defaults to ``"output"`` (relative to
        the applycling repo root). Can be an absolute path.

    Returns
    -------
    dict
        ``{"imported": N, "skipped": N, "errors": ["msg", ...]}``
    """
    root = Path(output_root).expanduser().resolve()
    if not root.is_dir():
        return {"imported": 0, "skipped": 0, "errors": [f"Output directory not found: {root}"]}

    store = get_store()

    # Load existing jobs for idempotency check.
    try:
        existing_jobs = store.load_jobs()
    except TrackerError:
        existing_jobs = []

    # Build set of (lowercase title, lowercase company) for quick lookup.
    existing_keys: set[tuple[str, str]] = set()
    for job in existing_jobs:
        key = (job.title.strip().lower(), job.company.strip().lower())
        existing_keys.add(key)

    imported = 0
    skipped = 0
    errors: list[str] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        info = _scan_folder(entry)
        if info is None:
            errors.append(f"Skipped malformed folder (no valid artifacts): {entry.name}")
            continue

        title = info["title"]
        company = info["company"]

        # Idempotency: skip if same title AND company already exist.
        key = (title.strip().lower(), company.strip().lower())
        if key in existing_keys:
            skipped += 1
            folder_prefix = "[dim]"
            continue

        try:
            # Create the job record.
            job = Job(
                id="",  # store assigns
                title=title,
                company=company,
                date_added="",  # store sets
                date_updated="",
                status="generated",
                source_url=info["source_url"],
                package_folder=info["package_folder"],
            )
            saved = store.save_job(job)

            # Attach artifacts by updating package_folder (tracker has no artifact table yet).
            # When jobs_service.attach_artifact is available (Ticket C), switch to that.
            if info["artifacts"]:
                store.update_job(saved.id, package_folder=info["package_folder"])

            imported += 1

        except TrackerError as e:
            errors.append(f"Failed to import {entry.name}: {e}")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }
