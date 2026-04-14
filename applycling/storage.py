"""Local file storage for resumes, jobs, and config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
RESUME_PATH = DATA_DIR / "resume.md"
JOBS_PATH = DATA_DIR / "jobs.json"
CONFIG_PATH = DATA_DIR / "config.json"
PROFILE_PATH = DATA_DIR / "profile.json"
STORIES_PATH = DATA_DIR / "stories.md"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class StorageError(Exception):
    """Raised when storage cannot satisfy a request."""


def save_resume(text: str) -> None:
    _ensure_dirs()
    RESUME_PATH.write_text(text, encoding="utf-8")


def load_resume() -> str:
    if not RESUME_PATH.exists():
        raise StorageError(
            "No base resume found. Run `applycling setup` first."
        )
    return RESUME_PATH.read_text(encoding="utf-8")


def save_config(config: dict[str, Any]) -> None:
    _ensure_dirs()
    # Merge into existing config so keys like provider/generate_run_log are preserved.
    existing: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.update(config)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise StorageError(
            "No config found. Run `applycling setup` first."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_jobs() -> list[dict[str, Any]]:
    if not JOBS_PATH.exists():
        return []
    raw = JOBS_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    return json.loads(raw)


def _write_jobs(jobs: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    JOBS_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def _next_job_id(jobs: list[dict[str, Any]]) -> str:
    nums = []
    for job in jobs:
        jid = job.get("id", "")
        if jid.startswith("job_"):
            try:
                nums.append(int(jid.split("_", 1)[1]))
            except ValueError:
                pass
    n = (max(nums) + 1) if nums else 1
    return f"job_{n:03d}"


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    """Append a new job, assigning it an auto-generated ID. Returns the saved job."""
    jobs = load_jobs()
    job = dict(job)
    job["id"] = _next_job_id(jobs)
    jobs.append(job)
    _write_jobs(jobs)
    return job


def load_job(job_id: str) -> dict[str, Any]:
    for job in load_jobs():
        if job.get("id") == job_id:
            return job
    raise StorageError(f"No job found with id '{job_id}'.")


def save_profile(profile: dict[str, Any]) -> None:
    _ensure_dirs()
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def load_profile() -> dict[str, Any] | None:
    if not PROFILE_PATH.exists():
        return None
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_stories() -> str | None:
    """Return contents of data/stories.md, or None if the file doesn't exist."""
    if not STORIES_PATH.exists():
        return None
    text = STORIES_PATH.read_text(encoding="utf-8").strip()
    return text or None


def save_stories(text: str) -> None:
    """Write stories to data/stories.md."""
    STORIES_PATH.write_text(text.strip(), encoding="utf-8")


def update_job_status(job_id: str, status: str) -> dict[str, Any]:
    jobs = load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            job["status"] = status
            _write_jobs(jobs)
            return job
    raise StorageError(f"No job found with id '{job_id}'.")
