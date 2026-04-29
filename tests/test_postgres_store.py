"""Tests for PostgresStore and store backend selection."""

from __future__ import annotations

import os
import uuid

import pytest

from applycling.tracker import Job, TrackerStore, get_store


# ── Helper ──────────────────────────────────────────────────────────────

def _clear_env_vars(monkeypatch):
    """Remove backend-related env vars so tests start from a clean slate."""
    for var in ("APPLYCLING_DB_BACKEND", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


# ── Backend selection tests ─────────────────────────────────────────────

def test_get_store_default_is_sqlite(monkeypatch):
    """When no env vars are set, get_store() returns SQLiteStore."""
    _clear_env_vars(monkeypatch)
    store = get_store()
    assert type(store).__name__ == "SQLiteStore"


def test_get_store_explicit_sqlite(monkeypatch):
    """APPLYCLING_DB_BACKEND=sqlite returns SQLiteStore."""
    _clear_env_vars(monkeypatch)
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "sqlite")
    store = get_store()
    assert type(store).__name__ == "SQLiteStore"


def test_get_store_postgres_requires_database_url(monkeypatch):
    """APPLYCLING_DB_BACKEND=postgres without DATABASE_URL raises an error."""
    _clear_env_vars(monkeypatch)
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "postgres")
    # Ensure DATABASE_URL is NOT set
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from applycling.tracker import TrackerError

    with pytest.raises(TrackerError, match="DATABASE_URL"):
        get_store()


def test_get_store_postgres_with_url(monkeypatch):
    """APPLYCLING_DB_BACKEND=postgres with DATABASE_URL returns PostgresStore."""
    _clear_env_vars(monkeypatch)
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "postgres")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://applycling:***@localhost:5432/applycling",
    )
    # PostgresStore.__init__ calls seed_local_user() which connects to the DB.
    # These routing tests only verify backend selection — mock out the DB call.
    monkeypatch.setattr(
        "applycling.tracker.postgres_store.seed_local_user", lambda url=None: uuid.UUID("00000000-0000-0000-0000-000000000001")
    )
    store = get_store()
    assert type(store).__name__ == "PostgresStore"


def test_notion_does_not_override_explicit_postgres(monkeypatch):
    """Even if Notion config would be present, explicit postgres wins.

    The get_store() function checks APPLYCLING_DB_BACKEND=postgres BEFORE
    touching any Notion code path. To prove this, we set up env for Postgres
    and verify that get_store() returns PostgresStore — the Notion probe
    is never reached.
    """
    _clear_env_vars(monkeypatch)
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "postgres")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://applycling:pass@localhost:5432/applycling",
    )

    # PostgresStore.__init__ calls seed_local_user() — mock the DB call.
    monkeypatch.setattr(
        "applycling.tracker.postgres_store.seed_local_user", lambda url=None: uuid.UUID("00000000-0000-0000-0000-000000000001")
    )

    # import notion_store so we can mock it — but get_store() won't use it
    from applycling.tracker import notion_store

    # If get_store() incorrectly probed Notion and found it disconnected,
    # it would fall back to SQLite. By mocking is_connected() to return True,
    # we verify that postgres still wins (Notion being connected doesn't
    # override the explicit DB backend).
    monkeypatch.setattr(notion_store, "is_connected", lambda: True)

    store = get_store()
    assert type(store).__name__ == "PostgresStore", (
        "Explicit APPLYCLING_DB_BACKEND=postgres must win over Notion"
    )


def test_save_job_rejects_non_uuid_id(monkeypatch):
    """Saving with a non-UUID id (e.g. job_001 from SQLite) raises TrackerError."""
    _clear_env_vars(monkeypatch)
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "postgres")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://applycling:***@localhost:5432/applycling",
    )
    monkeypatch.setattr(
        "applycling.tracker.postgres_store.seed_local_user",
        lambda url=None: uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    store = get_store()
    from applycling.tracker import TrackerError

    job = Job(
        id="job_001",
        title="Non-UUID",
        company="TestCo",
        date_added="",
        date_updated="",
        status="new",
    )
    with pytest.raises(TrackerError, match="UUID job IDs"):
        store.save_job(job)


def test_postgres_store_init_requires_url():
    """PostgresStore raises if no DATABASE_URL."""
    from applycling.tracker import TrackerError
    from applycling.tracker.postgres_store import PostgresStore

    # Temporarily clear env so we can test the constructor directly
    old = os.environ.pop("DATABASE_URL", None)
    try:
        with pytest.raises(TrackerError, match="DATABASE_URL"):
            PostgresStore(database_url="")  # empty triggers check
    finally:
        if old is not None:
            os.environ["DATABASE_URL"] = old


# ── CRUD tests (require real Postgres) ──────────────────────────────────

def _needs_postgres():
    """Return (database_url, store) or skip the test."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping Postgres CRUD test")
    from applycling.tracker.postgres_store import PostgresStore

    # Ensure a local user exists
    from applycling.db_seed import seed_local_user, LOCAL_USER_ID

    seed_local_user(database_url)

    # Truncate test data from prior runs so each test starts clean.
    # TRUNCATE ... CASCADE handles FK dependencies in the right order.
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute("TRUNCATE TABLE jobs, users RESTART IDENTITY CASCADE")
        conn.commit()

    # Re-seed the local user after truncate (well-known UUID is now gone).
    seed_local_user(database_url)

    store = PostgresStore(database_url)
    return database_url, store


def test_save_and_load_job():
    """Create a job, then load it back."""
    _, store = _needs_postgres()

    job = Job(
        id="",
        title="Software Engineer",
        company="TestCorp",
        date_added="",
        date_updated="",
        status="new",
        source_url="https://example.com/jobs/123",
    )
    saved = store.save_job(job)

    # Job should now have an id and dates populated
    assert saved.id, "save_job should assign an id"
    assert saved.date_added, "save_job should set date_added"
    assert saved.date_updated, "save_job should set date_updated"

    # UUID should be valid
    uuid.UUID(saved.id)

    # Load it back
    loaded = store.load_job(saved.id)
    assert loaded.id == saved.id
    assert loaded.title == "Software Engineer"
    assert loaded.company == "TestCorp"
    assert loaded.status == "new"
    assert loaded.source_url == "https://example.com/jobs/123"


def test_load_jobs_returns_list_ordered():
    """load_jobs returns jobs ordered by created_at DESC."""
    _, store = _needs_postgres()

    job1 = store.save_job(
        Job(
            id="",
            title="Job Alpha",
            company="A Corp",
            date_added="",
            date_updated="",
            status="new",
        )
    )
    job2 = store.save_job(
        Job(
            id="",
            title="Job Beta",
            company="B Corp",
            date_added="",
            date_updated="",
            status="new",
        )
    )

    jobs = store.load_jobs()
    assert isinstance(jobs, list)
    # Most recently created should be first
    titles = [j.title for j in jobs if j.id in (job1.id, job2.id)]
    assert titles == ["Job Beta", "Job Alpha"]


def test_load_job_not_found():
    """load_job raises TrackerError for missing job."""
    _, store = _needs_postgres()
    from applycling.tracker import TrackerError

    fake_id = str(uuid.uuid4())
    with pytest.raises(TrackerError, match="No job found"):
        store.load_job(fake_id)


def test_update_job_status():
    """update_job changes status and bumps date_updated."""
    _, store = _needs_postgres()

    job = store.save_job(
        Job(
            id="",
            title="Update Me",
            company="UpdateCo",
            date_added="",
            date_updated="",
            status="new",
        )
    )
    original_updated = job.date_updated

    updated = store.update_job(job.id, status="reviewing")
    assert updated.status == "reviewing"

    # date_updated should have changed
    assert updated.date_updated != original_updated, (
        "date_updated should be bumped on update"
    )

    # Load fresh and verify
    loaded = store.load_job(job.id)
    assert loaded.status == "reviewing"


def test_update_job_invalid_field():
    """update_job rejects fields not in ALLOWED_UPDATE_FIELDS."""
    _, store = _needs_postgres()
    from applycling.tracker import TrackerError

    job = store.save_job(
        Job(
            id="",
            title="Invalid Field Test",
            company="TestCo",
            date_added="",
            date_updated="",
            status="new",
        )
    )

    # 'date_added' is not in ALLOWED_UPDATE_FIELDS — must be rejected.
    with pytest.raises(TrackerError, match="Cannot update fields"):
        store.update_job(job.id, date_added="2025-01-01")


def test_update_job_no_fields():
    """update_job with no fields returns the job unchanged."""
    _, store = _needs_postgres()

    job = store.save_job(
        Job(
            id="",
            title="No-op Update",
            company="NoopCo",
            date_added="",
            date_updated="",
            status="new",
        )
    )
    updated = store.update_job(job.id)
    assert updated.id == job.id
    assert updated.title == "No-op Update"


def test_save_job_migrates_legacy_status():
    """Save with legacy status 'inbox' should store as 'new'."""
    _, store = _needs_postgres()

    job = store.save_job(
        Job(
            id="",
            title="Legacy Status",
            company="LegacyCo",
            date_added="",
            date_updated="",
            status="inbox",
        )
    )
    assert job.status == "new", f"Legacy status 'inbox' should migrate to 'new', got {job.status!r}"
    loaded = store.load_job(job.id)
    assert loaded.status == "new"


def test_save_job_with_preset_id():
    """save_job uses the provided id if set."""
    _, store = _needs_postgres()

    preset_id = str(uuid.uuid4())
    job = Job(
        id=preset_id,
        title="Preset ID Job",
        company="PresetCo",
        date_added="",
        date_updated="",
        status="new",
    )
    saved = store.save_job(job)
    assert saved.id == preset_id

    loaded = store.load_job(preset_id)
    assert loaded.title == "Preset ID Job"


def test_save_job_duplicate_id():
    """Saving a job with an existing UUID raises TrackerError."""
    _, store = _needs_postgres()
    from applycling.tracker import TrackerError

    shared_id = str(uuid.uuid4())
    job1 = Job(
        id=shared_id,
        title="First",
        company="DupCo",
        date_added="",
        date_updated="",
        status="new",
    )
    store.save_job(job1)

    job2 = Job(
        id=shared_id,
        title="Second",
        company="DupCo",
        date_added="",
        date_updated="",
        status="new",
    )
    with pytest.raises(TrackerError, match="Could not save"):
        store.save_job(job2)


def test_load_jobs_filters_deleted():
    """Soft-deleted jobs are excluded from load_jobs."""
    database_url, store = _needs_postgres()

    job = store.save_job(
        Job(
            id="",
            title="To Be Deleted",
            company="DelCo",
            date_added="",
            date_updated="",
            status="new",
        )
    )

    # Soft-delete the job directly in the DB
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute(
            "UPDATE jobs SET deleted_at = now() WHERE id = %s",
            (uuid.UUID(job.id),),
        )

    jobs = store.load_jobs()
    ids = [j.id for j in jobs]
    assert job.id not in ids, "Soft-deleted job should not appear in load_jobs"


def test_load_jobs_scoped_to_user():
    """Jobs from other users are NOT visible."""
    database_url, store = _needs_postgres()
    from applycling.db_seed import LOCAL_USER_ID

    # Create a second user directly
    other_user_id = uuid.uuid4()
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (other_user_id,),
        )
        # Insert a job for the other user
        other_job_id = uuid.uuid4()
        conn.execute(
            """
            INSERT INTO jobs (id, user_id, title, company, status, created_at, updated_at)
            VALUES (%s, %s, 'Other Job', 'OtherCo', 'new', now(), now())
            """,
            (other_job_id, other_user_id),
        )

    # Our store (scoped to LOCAL_USER_ID) should NOT see this job
    jobs = store.load_jobs()
    ids = [j.id for j in jobs]
    assert str(other_job_id) not in ids, (
        "Store should not see jobs from other users"
    )
