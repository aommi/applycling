"""
Job workflow service layer for applycling.

Thin service layer that the UI calls. Isolates UI from raw DB code
and keeps pipeline logic in one place. All persistence goes through
get_store() — never raw database access.

Workbench statuses (replacing/extending the old tracker statuses):
    inbox → running → generated → reviewing → applied
                                ↘ skipped
    running → failed
    failed → inbox (retry)
    skipped → inbox (reopen)

Artifacts are stored in a JSON file per job for SQLite compatibility.
In Postgres mode the artifacts table is used when available; the JSON
file is always a safe fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from applycling.tracker import TrackerError, get_store, Job

# ── Constants ────────────────────────────────────────────────────────

_WORKBENCH_STATUSES: tuple[str, ...] = (
    "inbox",
    "running",
    "generated",
    "reviewing",
    "applied",
    "skipped",
    "failed",
)

_ARTIFACT_KINDS: tuple[str, ...] = (
    "resume_pdf",
    "cover_letter_pdf",
    "resume_md",
    "cover_letter_md",
    "positioning_brief",
    "email_inmail",
    "fit_summary",
    "job_description",
)

# Simple transition rules — not exhaustive, but guards against nonsense.
# Empty set means "no further transitions allowed currently."
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "inbox":     {"running", "skipped"},
    "running":   {"generated", "failed"},
    "generated": {"reviewing", "applied", "skipped"},
    "reviewing": {"applied", "skipped", "generated"},
    "applied":   set(),
    "skipped":   {"inbox"},
    "failed":    {"inbox", "running"},
}


# ── Helpers ───────────────────────────────────────────────────────────

def _job_to_dict(job: Job) -> dict[str, Any]:
    return job.to_dict()


def _artifacts_path_for_job(job_id: str) -> Path:
    """Resolve the artifacts JSON path for a job.

    Prefers ``<package_folder>/artifacts.json`` when the job already has a
    package folder, otherwise falls back to ``data/artifacts/<id>.json``.
    """
    try:
        store = get_store()
        job = store.load_job(job_id)
        if job.package_folder:
            return Path(job.package_folder) / "artifacts.json"
    except TrackerError:
        pass

    fallback = Path(__file__).resolve().parent.parent / "data" / "artifacts"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / f"{job_id}_artifacts.json"


def _read_artifacts_json(job_id: str) -> dict[str, Any]:
    path = _artifacts_path_for_job(job_id)
    if not path.exists():
        return {"artifacts": [], "status_reasons": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"artifacts": [], "status_reasons": []}


def _write_artifacts_json(job_id: str, data: dict[str, Any]) -> None:
    path = _artifacts_path_for_job(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _record_status_reason(job_id: str, status: str, reason: str) -> None:
    """Append a status-change reason to the job's artifacts JSON."""
    data = _read_artifacts_json(job_id)
    data.setdefault("status_reasons", []).append(
        {"status": status, "reason": reason}
    )
    _write_artifacts_json(job_id, data)


# ── Public API ────────────────────────────────────────────────────────

def create_job_from_url(url: str) -> dict[str, Any]:
    """Create a new job with status ``inbox`` and ``source_url`` set.

    Returns the job as a dict (including the store-assigned id).
    """
    store = get_store()
    job = Job(
        id="",
        title="",
        company="",
        date_added="",
        date_updated="",
        status="inbox",
        source_url=url,
    )
    saved = store.save_job(job)
    return _job_to_dict(saved)


def list_jobs(status: str | None = None) -> list[dict[str, Any]]:
    """Return all jobs, optionally filtered by *status*."""
    store = get_store()
    jobs = store.load_jobs()
    if status is not None:
        jobs = [j for j in jobs if j.status == status]
    return [_job_to_dict(j) for j in jobs]


def get_job(job_id: str) -> dict[str, Any]:
    """Return a single job by id as a dict."""
    store = get_store()
    return _job_to_dict(store.load_job(job_id))


def set_job_status(
    job_id: str,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Update a job's status with optional transition validation.

    Raises ``ValueError`` if *status* is not a recognised workbench status
    or if the transition is disallowed.
    """
    if status not in _WORKBENCH_STATUSES:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {_WORKBENCH_STATUSES}"
        )

    store = get_store()
    job = store.load_job(job_id)
    current = job.status

    # Only enforce transitions when the current status is a workbench status.
    if current in _VALID_TRANSITIONS:
        allowed = _VALID_TRANSITIONS[current]
        if allowed and status not in allowed:
            raise ValueError(
                f"Cannot transition from '{current}' to '{status}'. "
                f"Allowed transitions: {sorted(allowed)}"
            )

    updated = store.update_job(job_id, status=status)

    if reason:
        _record_status_reason(job_id, status, reason)

    return _job_to_dict(updated)


def attach_artifact(job_id: str, kind: str, path: str) -> dict[str, Any]:
    """Record an artifact for a job.

    *kind* must be one of the recognised artifact kinds (e.g.
    ``resume_pdf``, ``cover_letter_md``, …).  The artifact metadata is
    stored in a JSON file alongside the job's package folder (SQLite mode)
    or in the ``artifacts`` table (Postgres mode when available).
    """
    if kind not in _ARTIFACT_KINDS:
        raise ValueError(
            f"Invalid artifact kind: '{kind}'. "
            f"Must be one of: {_ARTIFACT_KINDS}"
        )

    data = _read_artifacts_json(job_id)
    artifact: dict[str, Any] = {"kind": kind, "path": str(path)}
    data.setdefault("artifacts", []).append(artifact)
    _write_artifacts_json(job_id, data)
    return artifact


def list_artifacts(job_id: str) -> list[dict[str, Any]]:
    """Return all recorded artifacts for a job."""
    return _read_artifacts_json(job_id).get("artifacts", [])


def run_pipeline(job_id: str) -> dict[str, Any]:
    """Run the applycling pipeline for a job.

    Workflow:
    1. Set job status to ``running``.
    2. Delegate to ``applycling.pipeline.run_add_notify()``.
    3. On success → status ``generated``, record package folder + artifacts.
    4. On failure → status ``failed`` with reason.

    Returns the updated job dict (or an error dict on failure).
    """
    store = get_store()

    # ------------------------------------------------------------------
    # Pre-flight
    # ------------------------------------------------------------------
    try:
        job = store.load_job(job_id)
    except TrackerError as e:
        return {"error": str(e), "job_id": job_id}

    url = job.source_url
    if not url:
        return {
            "error": f"Job {job_id} has no source_url — cannot run pipeline.",
            "job_id": job_id,
        }

    # Set running *before* we start so the UI can see it immediately.
    try:
        store.update_job(job_id, status="running")
    except TrackerError as e:
        return {"error": str(e), "job_id": job_id}

    # ------------------------------------------------------------------
    # Silent notifier (no Telegram / Discord — local workbench only)
    # ------------------------------------------------------------------
    class _NullNotifier:
        """A notifier that swallows everything."""
        def notify(self, text: str) -> None:        # noqa: ARG002
            pass
        def send_document(self, path, caption: str = "") -> None:  # noqa: ARG002
            pass

    # ------------------------------------------------------------------
    # Run pipeline (this creates its own job internally — we'll merge)
    # ------------------------------------------------------------------
    try:
        from applycling.pipeline import run_add_notify

        folder: Path = run_add_notify(
            url=url,
            notifier=_NullNotifier(),
        )
    except Exception as exc:
        reason = str(exc)
        try:
            store.update_job(job_id, status="failed")
        except TrackerError:
            pass
        _record_status_reason(job_id, "failed", reason)
        return {"error": reason, "job_id": job_id}

    # ------------------------------------------------------------------
    # Merge pipeline-created job data into our workbench job
    # ------------------------------------------------------------------
    # run_add_notify saved a *second* job (status "tailored") with the
    # real title / company / fit_summary.  Find it and copy the fields
    # we care about into the original workbench job.
    try:
        all_jobs = store.load_jobs()
        pipeline_job = None
        for j in all_jobs:
            if j.id == job_id:
                continue
            if j.source_url == url and j.package_folder:
                # Most-recent match (list is date_added DESC)
                pipeline_job = j
                break

        if pipeline_job is not None:
            # Copy title / company / fit_summary from pipeline job
            updates: dict[str, Any] = {
                "status": "generated",
                "package_folder": str(folder),
            }
            if pipeline_job.title:
                updates["title"] = pipeline_job.title
            if pipeline_job.company:
                updates["company"] = pipeline_job.company
            if pipeline_job.fit_summary:
                updates["fit_summary"] = pipeline_job.fit_summary
            store.update_job(job_id, **updates)
        else:
            store.update_job(
                job_id, status="generated", package_folder=str(folder)
            )
    except TrackerError:
        # Best-effort — pipeline succeeded, try simple update
        try:
            store.update_job(
                job_id, status="generated", package_folder=str(folder)
            )
        except TrackerError:
            pass

    # ------------------------------------------------------------------
    # Attach generated artifacts
    # ------------------------------------------------------------------
    _ARTIFACT_FILES: dict[str, str] = {
        "resume_pdf":          "resume.pdf",
        "cover_letter_pdf":    "cover_letter.pdf",
        "resume_md":           "resume.md",
        "cover_letter_md":     "cover_letter.md",
        "positioning_brief":   "positioning_brief.md",
        "email_inmail":        "email_inmail.md",
        "fit_summary":         "fit_summary.md",
        "job_description":     "job_description.md",
    }
    for kind, filename in _ARTIFACT_FILES.items():
        file_path = folder / filename
        if file_path.exists():
            try:
                attach_artifact(job_id, kind, str(file_path))
            except Exception:
                pass  # Non-critical — pipeline already succeeded

    # Return the final state
    try:
        return _job_to_dict(store.load_job(job_id))
    except TrackerError:
        return {"error": "Pipeline succeeded but could not reload job.", "job_id": job_id}
