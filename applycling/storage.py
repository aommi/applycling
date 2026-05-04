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
LINKEDIN_PROFILE_PATH = DATA_DIR / "linkedin_profile.md"
APPLICANT_PROFILE_PATH = DATA_DIR / "applicant_profile.json"
TELEGRAM_CONFIG_PATH = DATA_DIR / "telegram.json"

# --- Application Profile schema ---

PROFILE_SCHEMA_VERSION = "1.0"

DEFERRED_PROFILE_FIELDS = [
    "work_auth",
    "sponsorship_needed",
    "relocation",
    "relocation_cities",
    "remote_preference",
    "comp_expectation",
    "notice_period",
    "earliest_start_date",
    "salary_expectations",
    "relocation_constraints",
    "detailed_job_preferences",
    "role_specific_positioning",
]


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


def load_profile() -> dict[str, Any]:
    """Return the unified Application Profile.

    Validates schema_version, backfills missing fields with sensible defaults,
    and returns {} when no profile exists. Never returns None.
    """
    import warnings

    unified: dict[str, Any] = {}
    if PROFILE_PATH.exists():
        try:
            unified = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            unified = {}

    # --- Schema version ---
    current_version = unified.get("schema_version")
    if not current_version:
        unified["schema_version"] = PROFILE_SCHEMA_VERSION
    elif current_version != PROFILE_SCHEMA_VERSION:
        warnings.warn(
            f"Profile schema version '{current_version}' differs from "
            f"current '{PROFILE_SCHEMA_VERSION}'. Some fields may be missing.",
            stacklevel=2,
        )

    # --- Backfill new fields with sensible defaults ---
    _NEW_FIELD_DEFAULTS: dict[str, Any] = {
        "portfolio": "",
        "personal_site": "",
        "target_role_family": "",
        "positioning_preference": "",
        "tracks": [],
        "salary_expectations": "",
        "relocation_constraints": "",
        "detailed_job_preferences": "",
        "story_bank_path": "",
        "role_specific_positioning": "",
    }
    for key, default in _NEW_FIELD_DEFAULTS.items():
        if key not in unified:
            unified[key] = default

    # Ensure deferred boolean fields exist as None when unset
    for key in ("sponsorship_needed", "relocation"):
        if key not in unified:
            unified[key] = None

    return unified


def save_profile(profile: dict[str, Any]) -> None:
    """Merge `profile` into the existing unified profile and persist.

    Preserves all existing fields not present in `profile`. Sets
    schema_version only if it is currently missing (never bumps).
    """
    _ensure_dirs()
    existing = load_profile()
    existing.update(profile)
    if not existing.get("schema_version"):
        existing["schema_version"] = PROFILE_SCHEMA_VERSION
    PROFILE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_stories() -> str | None:
    """Return contents of data/stories.md, or None if the file doesn't exist."""
    if not STORIES_PATH.exists():
        return None
    text = STORIES_PATH.read_text(encoding="utf-8").strip()
    return text or None


def save_stories(text: str) -> None:
    """Write stories to data/stories.md."""
    STORIES_PATH.write_text(text.strip(), encoding="utf-8")


def load_linkedin_profile() -> str | None:
    """Return contents of data/linkedin_profile.md, or None if not set."""
    if not LINKEDIN_PROFILE_PATH.exists():
        return None
    text = LINKEDIN_PROFILE_PATH.read_text(encoding="utf-8").strip()
    return text or None


def save_linkedin_profile(text: str) -> None:
    """Write LinkedIn profile text to data/linkedin_profile.md."""
    _ensure_dirs()
    LINKEDIN_PROFILE_PATH.write_text(text.strip(), encoding="utf-8")


def load_applicant_profile() -> dict[str, Any]:
    """Deprecated — use load_profile() instead.

    Returns the deferred-fields subset of the unified profile so existing
    callers (e.g. setup wizard showing current values) still work.
    """
    import warnings

    warnings.warn(
        "load_applicant_profile() is deprecated. Use load_profile().",
        DeprecationWarning,
        stacklevel=2,
    )
    unified = load_profile()
    return {
        k: v for k, v in unified.items()
        if k in DEFERRED_PROFILE_FIELDS and v is not None
    }


def save_applicant_profile(profile: dict[str, Any]) -> None:
    """Deprecated — use save_profile() instead.

    Merges fields into the unified profile. Preserves all other fields.
    """
    import warnings

    warnings.warn(
        "save_applicant_profile() is deprecated. Use save_profile().",
        DeprecationWarning,
        stacklevel=2,
    )
    save_profile(profile)


def profile_completeness(profile: dict) -> str:
    """Return profile completeness state.

    Returns one of: "missing_contact", "missing_resume", "ready",
    "enriched", "complete".

    Rules:
      missing_contact: name or email is empty (checked first)
      missing_resume: name + email ok, but RESUME_PATH doesn't exist
      ready: name + email + resume exist
      enriched: ready + >= 3 fields in DEFERRED_PROFILE_FIELDS are non-empty
      complete: ready + ALL fields in DEFERRED_PROFILE_FIELDS are non-empty
                (Boolean False counts as non-empty; None does not)
    """
    if not profile.get("name") or not profile.get("email"):
        return "missing_contact"
    if not RESUME_PATH.exists():
        return "missing_resume"

    deferred_count = sum(
        1 for k in DEFERRED_PROFILE_FIELDS
        if profile.get(k) not in (None, "", [])
    )
    if deferred_count == len(DEFERRED_PROFILE_FIELDS):
        return "complete"
    if deferred_count >= 3:
        return "enriched"
    return "ready"


def missing_required_fields(profile: dict, required: list[str]) -> list[str]:
    """Return field names from `required` that are missing/unset in profile.

    "Missing" means: None, empty string (""), or empty list ([]).
    Boolean fields: False is NOT missing — it's a valid sentinel meaning "no."
    Use None for "unset / user hasn't answered."

    This is consistent with profile_completeness(), which counts False as
    non-empty when tallying deferred fields.
    """

    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and value == "":
            return True
        if isinstance(value, list) and len(value) == 0:
            return True
        return False  # bool False and int 0 are valid sentinels

    return [f for f in required if _is_missing(profile.get(f))]


def load_telegram_config() -> dict[str, Any]:
    """Return Telegram config dict with 'bot_token' and 'chat_id' keys."""
    if not TELEGRAM_CONFIG_PATH.exists():
        raise StorageError("Telegram not configured. Run: applycling telegram setup")
    return json.loads(TELEGRAM_CONFIG_PATH.read_text(encoding="utf-8"))


def save_telegram_config(bot_token: str, chat_id: str) -> None:
    _ensure_dirs()
    TELEGRAM_CONFIG_PATH.write_text(
        json.dumps({"bot_token": bot_token, "chat_id": chat_id}, indent=2),
        encoding="utf-8",
    )


def update_job_status(job_id: str, status: str) -> dict[str, Any]:
    jobs = load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            job["status"] = status
            _write_jobs(jobs)
            return job
    raise StorageError(f"No job found with id '{job_id}'.")
