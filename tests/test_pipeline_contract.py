"""Tests for applycling.pipeline contract.

Verifies that the pipeline dataclasses and entry points are well-formed
and ready for external orchestrators (e.g., OpenClaw) to use.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from applycling import pipeline, tracker, queue


def test_pipeline_context_creation():
    """Verify PipelineContext can be created with required fields."""
    ctx = pipeline.PipelineContext(
        data_dir=Path("."),
        output_dir=Path("./output"),
        profile={"name": "Test User"},
        resume="## Test Resume",
        stories="",
        linkedin_profile=None,
        config={"model": "test"},
        model="test-model",
        provider="ollama",
        tracker_store=None,
    )

    assert ctx.model == "test-model"
    assert ctx.provider == "ollama"
    assert ctx.profile["name"] == "Test User"


def test_pipeline_step_creation():
    """Verify PipelineStep tracks timing, output, and status."""
    step = pipeline.PipelineStep("test_step", output_file="test.md")

    # Initial state
    assert step.name == "test_step"
    assert step.output_file == "test.md"
    assert step.status == "ok"
    assert step.output == ""
    assert step.tokens_in == 0
    assert step.tokens_out == 0

    # Mark as completed
    step.mark_ok("test output")
    assert step.output == "test output"
    assert step.status == "ok"
    assert step.finished_at is not None

    # Convert to dict
    d = step.to_dict()
    assert d["name"] == "test_step"
    assert d["output_file"] == "test.md"
    assert d["status"] == "ok"
    assert "duration_seconds" in d
    assert "started_at" in d
    assert "finished_at" in d


def test_pipeline_step_streaming():
    """Verify PipelineStep.streaming context manager collects output."""
    step = pipeline.PipelineStep("stream_test")
    step.prompt = "test prompt"

    chunks = []

    def on_chunk(chunk: str):
        chunks.append(chunk)

    with step.streaming(on_chunk=on_chunk) as collect:
        collect("hello ")
        collect("world")

    assert step.output == "hello world"
    assert chunks == ["hello ", "world"]
    assert step.status == "ok"
    assert step.finished_at is not None


def test_pipeline_step_skipped_when_empty():
    """Verify PipelineStep is marked as skipped when output is empty."""
    step = pipeline.PipelineStep("empty_test")

    with step.streaming() as collect:
        pass  # Don't collect anything

    assert step.output == ""
    assert step.status == "skipped"


def test_pipeline_step_mark_failed():
    """Verify PipelineStep.mark_failed records error."""
    step = pipeline.PipelineStep("failed_test")

    try:
        raise ValueError("Test error")
    except Exception as e:
        step.mark_failed(e)

    assert step.status == "failed"
    assert "Test error" in step.error
    assert step.finished_at is not None


def test_pipeline_run_aggregation():
    """Verify PipelineRun aggregates step metadata."""
    steps = [
        pipeline.PipelineStep("step1", output_file="out1.md"),
        pipeline.PipelineStep("step2", output_file="out2.md"),
    ]
    steps[0].tokens_in = 100
    steps[0].tokens_out = 50
    steps[1].tokens_in = 200
    steps[1].tokens_out = 100

    _now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    run = pipeline.PipelineRun(
        run_id="test_run",
        started_at=_now,
        finished_at=_now,
        model="test-model",
        provider="ollama",
        steps=steps,
    )

    totals = run.total_tokens()
    assert totals["tokens_in"] == 300
    assert totals["tokens_out"] == 150
    assert totals["total_tokens"] == 450


def test_add_result_creation():
    """Verify AddResult holds all output artefacts."""
    job = tracker.Job(
        id="job_001",
        title="Test Job",
        company="Test Corp",
        date_added="2025-01-01T00:00:00Z",
        date_updated="2025-01-01T00:00:00Z",
    )

    result = pipeline.AddResult(
        run_id="run_001",
        job=job,
        resume_tailored="## Tailored Resume",
        fit_summary="Good fit",
        strategy="## Strategy",
        positioning_brief="## Brief",
        cover_letter="Dear Hiring Manager",
        email_inmail="Subject: Application",
        job_description="## Job",
    )

    assert result.job.title == "Test Job"
    assert result.resume_tailored == "## Tailored Resume"
    assert result.strategy == "## Strategy"
    assert result.cover_letter == "Dear Hiring Manager"


def test_checkpoint_step_ordering():
    """Verify checkpoint resolution correctly identifies steps to skip."""
    # Test skipping before first step
    steps = pipeline.get_step_names_before_checkpoint("role_intel")
    assert steps == []

    # Test skipping before middle step
    steps = pipeline.get_step_names_before_checkpoint("positioning_brief")
    assert steps == ["role_intel", "resume_tailor", "profile_summary", "format_resume"]

    # Test skipping before last step
    steps = pipeline.get_step_names_before_checkpoint("fit_summary")
    assert len(steps) == 7  # All steps before fit_summary


def test_compute_token_costs():
    """Verify token cost computation works with zero tokens."""
    steps = [
        pipeline.PipelineStep("step1"),
        pipeline.PipelineStep("step2"),
    ]

    totals, costs = pipeline.compute_token_costs(steps)

    assert totals["tokens_in"] == 0
    assert totals["tokens_out"] == 0
    assert totals["total_tokens"] == 0
    assert isinstance(costs, dict)
    assert "claude_sonnet" in costs
    assert "gpt4o" in costs


def test_memory_queue_basic_flow():
    """Verify MemoryQueue handles enqueue/dequeue/complete flow."""
    q = queue.MemoryQueue()

    # Enqueue
    job1 = q.enqueue("https://example.com/job1", source="test")
    assert job1.id.startswith("job_")
    assert job1.url == "https://example.com/job1"
    assert job1.claimed_by is None

    # Dequeue
    claimed = q.dequeue(claimer_id="worker_1")
    assert claimed is not None
    assert claimed.id == job1.id
    assert claimed.claimed_by == "worker_1"
    assert claimed.claimed_at is not None

    # Complete
    q.mark_completed(job1.id)
    # After completion, dequeue should return None (job is gone)
    nothing = q.dequeue(claimer_id="worker_1")
    assert nothing is None


def test_memory_queue_claim_once():
    """Verify MemoryQueue doesn't claim already-claimed jobs."""
    q = queue.MemoryQueue()

    job = q.enqueue("https://example.com/job", source="test")
    claimed1 = q.dequeue(claimer_id="worker_1")
    assert claimed1 is not None

    # Try to dequeue again with different worker — should get None
    claimed2 = q.dequeue(claimer_id="worker_2")
    assert claimed2 is None


def test_memory_queue_mark_failed():
    """Verify MemoryQueue mark_failed releases the claim for retry."""
    q = queue.MemoryQueue()

    job = q.enqueue("https://example.com/job", source="test")
    claimed = q.dequeue(claimer_id="worker_1")
    assert claimed.claimed_by == "worker_1"

    # Mark as failed
    q.mark_failed(job.id, "Network error")

    # Now another worker should be able to claim it
    retried = q.dequeue(claimer_id="worker_2")
    assert retried is not None
    assert retried.id == job.id
    assert retried.claimed_by == "worker_2"
    assert retried.error == "Network error"


def test_queue_list_methods():
    """Verify MemoryQueue list methods return expected results."""
    q = queue.MemoryQueue()

    q.enqueue("url1")
    q.enqueue("url2")
    claimed = q.dequeue()
    q.mark_failed(claimed.id, "error")

    pending = q.list_pending()
    failed = q.list_failed()

    assert len(pending) >= 1
    assert len(failed) >= 1


def test_pipeline_step_dict_serialization():
    """Verify PipelineStep can be serialized to run_log format."""
    step = pipeline.PipelineStep("test", output_file="test.md")
    step.prompt = "test prompt"
    step.mark_ok("test output")

    # Basic dict (without content)
    d = step.to_dict()
    assert "prompt_text" not in d  # Excluded from basic dict
    assert "output_text" not in d

    # Full dict (with content)
    d_full = step.to_dict_with_content()
    assert d_full["prompt_text"] == "test prompt"
    assert d_full["output_text"] == "test output"


if __name__ == "__main__":
    # Run tests if executed directly
    import sys

    test_functions = [
        name for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]

    failed = 0
    for test_name in test_functions:
        try:
            globals()[test_name]()
            print(f"✓ {test_name}")
        except AssertionError as e:
            print(f"✗ {test_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_name}: {type(e).__name__}: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    else:
        print(f"\n✓ All {len(test_functions)} tests passed!")
