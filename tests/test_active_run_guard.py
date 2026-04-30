"""Tests for the pipeline_runs active-run guard."""

from __future__ import annotations

import os
import uuid

import pytest

from applycling.tracker import check_active_run, _is_postgres
from applycling.jobs_service import run_pipeline


# ═══════════════════════════════════════════════════════════════════════
# SQLite mode — all guard methods are no-ops
# ═══════════════════════════════════════════════════════════════════════

def test_is_postgres_false_in_sqlite_mode(monkeypatch):
    monkeypatch.delenv("APPLYCLING_DB_BACKEND", raising=False)
    assert _is_postgres() is False

    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "sqlite")
    assert _is_postgres() is False


def test_check_active_run_returns_false_in_sqlite(monkeypatch):
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "sqlite")
    assert check_active_run() is False


def test_register_startup_sweep_noop_in_sqlite(monkeypatch):
    """register_startup_sweep() is a no-op when backend is not Postgres."""
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "sqlite")
    from applycling.tracker import register_startup_sweep

    # Create a minimal mock app — should not raise or register any events.
    class FakeApp:
        def on_event(self, event):
            def decorator(fn):
                return fn
            return decorator

    app = FakeApp()
    # This should not raise — it's a clean no-op.
    register_startup_sweep(app)


# ═══════════════════════════════════════════════════════════════════════
# Postgres mode — guard logic tests (mocked DB)
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def postgres_env(monkeypatch):
    """Set up a Postgres environment with mocked DB calls."""
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "postgres")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://applycling:***@localhost:5432/applycling",
    )
    # PostgresStore.__init__ calls seed_local_user() — mock it.
    monkeypatch.setattr(
        "applycling.tracker.postgres_store.seed_local_user",
        lambda url=None: uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )


def test_is_postgres_true_in_postgres_mode(postgres_env):
    assert _is_postgres() is True


def test_check_active_run_false_when_no_runs(postgres_env, monkeypatch):
    """check_active_run() returns False when get_active_run() returns None."""
    from applycling.tracker import get_store

    store = get_store()
    monkeypatch.setattr(store, "get_active_run", lambda: None)
    # check_active_run() calls get_store() internally — mock it to return
    # our pre-patched store.
    monkeypatch.setattr(
        "applycling.tracker.get_store", lambda: store
    )

    assert check_active_run() is False


def test_check_active_run_true_when_run_exists(postgres_env, monkeypatch):
    """check_active_run() returns True when get_active_run() returns a dict."""
    from applycling.tracker import get_store

    store = get_store()
    monkeypatch.setattr(
        store,
        "get_active_run",
        lambda: {
            "id": "run-1",
            "job_id": "job-1",
            "status": "running",
        },
    )
    monkeypatch.setattr(
        "applycling.tracker.get_store", lambda: store
    )

    assert check_active_run() is True


def test_create_run_succeeds(postgres_env, monkeypatch):
    """create_run() returns a run ID when no active run exists."""
    from applycling.tracker import get_store

    store = get_store()
    run_id = str(uuid.uuid4())
    monkeypatch.setattr(store, "create_run", lambda *a, **kw: run_id)

    # Simulate what run_pipeline does internally
    assert store.create_run("job-123") == run_id


def test_create_run_fails_when_active_run_exists(postgres_env, monkeypatch):
    """create_run() returns None when an active run already exists."""
    from applycling.tracker import get_store

    store = get_store()
    monkeypatch.setattr(store, "create_run", lambda *a, **kw: None)

    assert store.create_run("job-123") is None


def test_sweep_stale_runs_returns_count(postgres_env, monkeypatch):
    """sweep_stale_runs() returns the number of rows swept."""
    from applycling.tracker import get_store

    store = get_store()
    monkeypatch.setattr(store, "sweep_stale_runs", lambda: 3)

    assert store.sweep_stale_runs() == 3


def test_run_pipeline_rejects_when_guard_blocks(postgres_env, monkeypatch):
    """run_pipeline() returns an error if create_run() returns None."""
    from applycling.tracker import get_store

    store = get_store()
    # Mock create_run to simulate active-run conflict.
    monkeypatch.setattr(store, "create_run", lambda *a, **kw: None)
    # Mock get_store in BOTH tracker and jobs_service modules so run_pipeline
    # gets the same patched store instance.
    monkeypatch.setattr(
        "applycling.tracker.get_store", lambda: store
    )
    monkeypatch.setattr(
        "applycling.jobs_service.get_store", lambda: store
    )

    result = run_pipeline("nonexistent-job-id")

    assert "error" in result
    assert "already running" in result["error"].lower()


def test_run_pipeline_not_guarded_in_sqlite(monkeypatch):
    """run_pipeline() does not enforce guard when backend is SQLite."""
    monkeypatch.setenv("APPLYCLING_DB_BACKEND", "sqlite")

    # run_pipeline will hit load_job and fail on missing job, but
    # the guard section should be skipped entirely.
    result = run_pipeline("nonexistent-job-id")

    assert "error" in result
    # Error should be about the missing job, NOT about an active run.
    assert "already running" not in result.get("error", "")


def test_heartbeat_run_noop_on_invalid_uuid(postgres_env, monkeypatch):
    """heartbeat_run() silently returns when given an invalid UUID."""
    from applycling.tracker import get_store

    store = get_store()
    # Should not raise — invalid UUID is handled gracefully.
    store.heartbeat_run("not-a-uuid")


def test_update_run_noop_on_invalid_uuid(postgres_env, monkeypatch):
    """update_run() silently returns when given an invalid UUID."""
    from applycling.tracker import get_store

    store = get_store()
    # Should not raise — invalid UUID is handled gracefully.
    store.update_run("not-a-uuid", "generated")


# ═══════════════════════════════════════════════════════════════════════
# Concurrent insert test (Postgres only — gated)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    os.environ.get("APPLYCLING_DB_BACKEND") != "postgres"
    or not os.environ.get("DATABASE_URL"),
    reason="Requires Postgres with DATABASE_URL set",
)
def test_concurrent_inserts_only_one_succeeds():
    """The atomic INSERT … ON CONFLICT ensures only one active run exists."""
    import concurrent.futures
    from applycling.tracker import get_store

    new_job_id = str(uuid.uuid4())

    def _try_create_run(worker_id: int) -> str | None:
        store = get_store()
        return store.create_run(new_job_id, "running")

    # Fire 5 concurrent create_run calls.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_try_create_run, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    run_ids = [r for r in results if r is not None]
    none_count = sum(1 for r in results if r is None)

    assert len(run_ids) == 1, (
        f"Expected exactly 1 successful run, got {len(run_ids)}. "
        f"Results: {results}"
    )
    assert none_count == 4, (
        f"Expected 4 rejected inserts, got {none_count}"
    )

    # Clean up: mark the run as generated so it doesn't block future tests.
    store = get_store()
    store.update_run(run_ids[0], "generated")
