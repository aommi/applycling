"""Test the applycling library API for external orchestrators (e.g., OpenClaw).

This test verifies that the public API surface is usable programmatically
without the CLI, suitable for external orchestrators.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from applycling import pipeline, tracker, queue


def test_pipeline_context_from_config_signature():
    """Verify PipelineContext.from_config has the right signature."""
    # This would normally load from data/ directory
    # For this test, we just verify the signature exists
    assert hasattr(pipeline.PipelineContext, "from_config")
    assert callable(pipeline.PipelineContext.from_config)


def test_run_add_signature():
    """Verify run_add has the expected function signature."""
    import inspect

    sig = inspect.signature(pipeline.run_add)
    params = list(sig.parameters.keys())

    # Required positional/keyword args
    assert "job_url" in params
    assert "job_title" in params
    assert "job_company" in params
    assert "job_description" in params
    assert "context" in params

    # Keyword-only args (for callbacks and options)
    assert "on_chunk" in params
    assert "on_status" in params
    assert "on_gate" in params
    assert "want_summary" in params
    assert "render_pdf" in params


def test_persist_add_result_signature():
    """Verify persist_add_result has the expected function signature."""
    import inspect

    sig = inspect.signature(pipeline.persist_add_result)
    params = list(sig.parameters.keys())

    assert "result" in params
    assert "output_root" in params
    assert "generate_docx" in params
    assert "generate_run_log" in params


def test_queue_store_interface():
    """Verify QueueStore ABC has expected methods."""
    methods = ["enqueue", "dequeue", "mark_completed", "mark_failed", "list_pending", "list_failed"]
    for method in methods:
        assert hasattr(queue.QueueStore, method)


def test_memory_queue_interface():
    """Verify MemoryQueue implements full QueueStore interface."""
    q = queue.MemoryQueue()

    # Should have all required methods
    assert callable(q.enqueue)
    assert callable(q.dequeue)
    assert callable(q.mark_completed)
    assert callable(q.mark_failed)
    assert callable(q.list_pending)
    assert callable(q.list_failed)

    # Basic operations should work
    job = q.enqueue("https://example.com/job")
    assert job.id is not None
    assert job.url == "https://example.com/job"


def test_pipeline_step_context_manager():
    """Verify PipelineStep.streaming works as context manager."""
    step = pipeline.PipelineStep("test")

    output_parts = []

    def capture_chunk(chunk: str):
        output_parts.append(chunk)

    with step.streaming(on_chunk=capture_chunk) as collect:
        collect("hello")
        collect(" ")
        collect("world")

    assert step.output == "hello world"
    assert output_parts == ["hello", " ", "world"]


def test_pipeline_run_cost_computation():
    """Verify compute_token_costs returns correct structure."""
    steps = [
        pipeline.PipelineStep("step1"),
        pipeline.PipelineStep("step2"),
    ]
    # Set prompt and output so tiktoken can count tokens
    steps[0].prompt = "a" * 4000  # 1000 tokens at 4 chars/token
    steps[0].output = "b" * 2000  # 500 tokens
    steps[1].prompt = "c" * 8000  # 2000 tokens
    steps[1].output = "d" * 4000  # 1000 tokens

    # Compute costs
    totals, costs = pipeline.compute_token_costs(steps)

    # Verify structure
    assert isinstance(totals, dict)
    assert "tokens_in" in totals
    assert "tokens_out" in totals
    assert "total_tokens" in totals

    # Verify cost estimates exist for common models
    assert isinstance(costs, dict)
    assert "claude_sonnet" in costs
    assert "gpt4o" in costs
    assert "gemini_2_5_pro" in costs

    # Should have calculated non-zero tokens (if tiktoken available)
    # or zero if using fallback (no prompt/output initially)
    assert totals["total_tokens"] >= 0


def test_add_result_has_all_artefacts():
    """Verify AddResult carries all generated artefacts."""
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
        resume_tailored="## Tailored",
        fit_summary="Good fit",
        strategy="## Strategy",
        positioning_brief="## Brief",
        cover_letter="Dear Hiring Manager",
        email_inmail="Subject: Application",
        job_description="## JD",
        company_context="## Company",
    )

    # All artefacts should be accessible
    assert result.resume_tailored is not None
    assert result.fit_summary is not None
    assert result.strategy is not None
    assert result.positioning_brief is not None
    assert result.cover_letter is not None
    assert result.email_inmail is not None
    assert result.job_description is not None
    assert result.company_context is not None


def test_checkpoint_utilities():
    """Verify checkpoint utilities work correctly."""
    # First checkpoint skips nothing
    assert pipeline.get_step_names_before_checkpoint("role_intel") == []

    # Middle checkpoint skips all preceding steps (not including itself)
    skipped = pipeline.get_step_names_before_checkpoint("cover_letter")
    assert "role_intel" in skipped
    assert "resume_tailor" in skipped
    assert "positioning_brief" in skipped  # comes before cover_letter
    assert "cover_letter" not in skipped  # checkpoint itself is not skipped
    assert "email_inmail" not in skipped  # comes after

    # Invalid checkpoint raises error
    try:
        pipeline.get_step_names_before_checkpoint("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # Expected


def test_load_package_artifacts_structure():
    """Verify load_package_artifacts returns correct structure."""
    artifacts = pipeline.load_package_artifacts(Path("/nonexistent"))

    # Should return dict even if folder doesn't exist
    assert isinstance(artifacts, dict)
    assert len(artifacts) == 0


def test_tracker_job_dataclass():
    """Verify tracker.Job works as expected."""
    job = tracker.Job(
        id="job_123",
        title="Senior Engineer",
        company="TechCorp",
        date_added="2025-01-01T00:00:00Z",
        date_updated="2025-01-01T00:00:00Z",
        status="tailored",
        source_url="https://example.com/job",
        fit_summary="Strong match",
    )

    assert job.id == "job_123"
    assert job.title == "Senior Engineer"
    assert job.company == "TechCorp"
    assert job.status == "tailored"

    # Can convert to dict
    d = job.to_dict()
    assert d["id"] == "job_123"
    assert d["title"] == "Senior Engineer"


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
