"""Regression guard for applycling pipeline structure.

This test ensures that structural changes to the pipeline (step ordering, output files,
run_log shape) are caught. It does NOT assert on LLM output content (which is non-deterministic).

The test uses a stub LLM that returns canned strings per step, ensuring deterministic runs
that we can use to validate the pipeline structure without flaky LLM-based comparisons.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Adjust path to find applycling module
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures" / "regression"


class StubLLM:
    """Deterministic LLM stub for regression testing.

    Returns the same canned output for each step, keyed by step name.
    """

    responses = {
        "role_intel": "## Identified niche\nSenior platform engineer with distributed systems expertise.\n\n## Tooling or domain gaps\nNo significant gaps — your experience aligns well.\n\n## ATS match score\n92/100",
        "resume_tailor": "# Jane Doe\nTailored resume content for platform role.",
        "profile_summary": "Experienced platform engineer with deep backend expertise.",
        "format_resume": "# Jane Doe\n\nFormatted resume content.",
        "positioning_brief": "## Positioning Strategy\nLead with distributed systems and scale experience.",
        "cover_letter": "Dear Hiring Manager,\nI am excited about this role.",
        "email_inmail": "Subject: Jane Doe - Senior Engineer\n\nHi there,\nI am interested in this role.",
        "fit_summary": "Strong fit: 9/10. Platform experience, system design, mentoring.",
    }

    def __init__(self):
        self.call_count = {}

    def __call__(self, *args, **kwargs) -> list[str]:
        """Mock LLM call that returns canned response in chunks."""
        # This will be mocked into llm._stream_chat
        # Return chunks of the canned response
        raise NotImplementedError("Should be replaced by pytest mocks")


def stub_stream_chat(step_name: str):
    """Factory for mocking llm._stream_chat to return canned responses."""

    def _inner(model: str, prompt: str, provider: str = "ollama"):
        response = StubLLM.responses.get(step_name, "")
        # Yield in small chunks to simulate streaming
        chunk_size = 10
        for i in range(0, len(response), chunk_size):
            yield response[i : i + chunk_size]

    return _inner


def load_fixture(filename: str) -> str:
    """Load a fixture file."""
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared setup: build a PipelineContext + run the pipeline with mocked LLM
# ---------------------------------------------------------------------------

def _make_context_and_run(tmp_path: Path, on_gate=None):
    """Run the full pipeline with stub LLM and mocked render. Return (result, folder)."""
    from applycling import pipeline, tracker

    profile = json.loads(load_fixture("profile.json"))
    resume = load_fixture("base_resume.md")
    job_description = load_fixture("job_description.txt")

    # In-memory tracker store
    class _MemoryTrackerStore(tracker.TrackerStore):
        def __init__(self):
            self._jobs: dict[str, tracker.Job] = {}

        def save_job(self, job: tracker.Job) -> tracker.Job:
            import uuid, datetime as dt
            now_iso = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z"
            saved = tracker.Job(
                id=job.id or f"job_{uuid.uuid4().hex[:8]}",
                title=job.title,
                company=job.company,
                date_added=job.date_added or now_iso,
                date_updated=job.date_updated or now_iso,
                status=job.status,
                source_url=job.source_url,
                fit_summary=job.fit_summary,
            )
            self._jobs[saved.id] = saved
            return saved

        def load_jobs(self) -> list[tracker.Job]:
            return list(self._jobs.values())

        def load_job(self, job_id: str) -> tracker.Job:
            if job_id not in self._jobs:
                raise tracker.TrackerError(f"Not found: {job_id}")
            return self._jobs[job_id]

        def update_job(self, job_id: str, **fields) -> tracker.Job:
            job = self.load_job(job_id)
            import dataclasses
            updated = dataclasses.replace(job, **fields)
            self._jobs[job_id] = updated
            return updated

    ctx = pipeline.PipelineContext(
        data_dir=Path("."),
        output_dir=tmp_path / "output",
        profile=profile,
        resume=resume,
        stories="",
        linkedin_profile=None,
        config={"model": "stub-model", "provider": "stub"},
        model="stub-model",
        provider="stub",
        tracker_store=_MemoryTrackerStore(),
    )

    # The pipeline calls llm._stream_chat for each step. We use a side_effect
    # list that returns the canned response for each step in order.
    # Steps in order: role_intel, resume_tailor, profile_summary, format_resume,
    # positioning_brief, cover_letter, email_inmail, fit_summary
    ordered_responses = [
        StubLLM.responses["role_intel"],
        StubLLM.responses["resume_tailor"],
        StubLLM.responses["profile_summary"],
        StubLLM.responses["format_resume"],
        StubLLM.responses["positioning_brief"],
        StubLLM.responses["cover_letter"],
        StubLLM.responses["email_inmail"],
        StubLLM.responses["fit_summary"],
    ]

    def make_side_effect(responses):
        it = iter(responses)
        def side_effect(model, prompt, provider="ollama"):
            resp = next(it, "")
            chunk_size = 20
            for i in range(0, max(len(resp), 1), chunk_size):
                yield resp[i:i + chunk_size]
        return side_effect

    # Mock render functions to avoid Playwright
    with patch("applycling.llm._stream_chat", side_effect=make_side_effect(ordered_responses)), \
         patch("applycling.render.render_resume") as mock_render, \
         patch("applycling.render.markdown_to_html", return_value="<html/>") as mock_html, \
         patch("applycling.render.html_to_pdf") as mock_pdf:

        # render.render_resume must write resume.md for package.assemble to find it
        def _fake_render_resume(markdown, folder, title=""):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "resume.md").write_text(markdown, encoding="utf-8")
            (folder / "resume.html").write_text("<html/>", encoding="utf-8")
            (folder / "resume.pdf").write_bytes(b"%PDF-fake")

        mock_render.side_effect = _fake_render_resume

        def _fake_html_to_pdf(html_path, pdf_path):
            pdf_path.write_bytes(b"%PDF-fake")

        mock_pdf.side_effect = _fake_html_to_pdf

        result = pipeline.run_add(
            job_url="https://example.com/job/123",
            job_title="Senior Software Engineer",
            job_company="ExampleCorp",
            job_description=job_description,
            context=ctx,
            want_summary=True,
            render_pdf=True,
            on_gate=on_gate,
        )

        folder = pipeline.persist_add_result(
            result,
            output_root=tmp_path / "output",
            generate_run_log=True,
        )

    return result, folder


def test_regression_step_ordering(tmp_path):
    """Verify that pipeline steps are executed in the correct order."""
    result, folder = _make_context_and_run(tmp_path)

    step_names = [s.name for s in result.run.steps]

    # company_context step only added when company_url is provided; not here.
    # Core steps must appear in this order:
    expected_order = [
        "role_intel",
        "resume_tailor",
        "profile_summary",
        "format_resume",
        "positioning_brief",
        "cover_letter",
        "email_inmail",
        "fit_summary",
    ]

    # Verify all expected steps are present
    for step in expected_order:
        assert step in step_names, f"Step '{step}' missing from run. Got: {step_names}"

    # Verify ordering (relative positions match expected)
    positions = {name: step_names.index(name) for name in expected_order if name in step_names}
    for i in range(len(expected_order) - 1):
        a, b = expected_order[i], expected_order[i + 1]
        if a in positions and b in positions:
            assert positions[a] < positions[b], (
                f"Step '{a}' (pos {positions[a]}) should come before '{b}' (pos {positions[b]})"
            )


def test_regression_output_files(tmp_path):
    """Verify that output files are created with correct names."""
    result, folder = _make_context_and_run(tmp_path)

    assert folder.exists(), f"Package folder not created: {folder}"

    # Required files
    required_files = [
        "resume.md",
        "resume.html",
        "resume.pdf",
        "fit_summary.md",
        "strategy.md",
        "positioning_brief.md",
        "cover_letter.md",
        "email_inmail.md",
        "job_description.md",
        "job.json",
        "run_log.json",
    ]

    for filename in required_files:
        path = folder / filename
        assert path.exists(), f"Expected output file missing: {filename} (in {folder})"
        assert path.stat().st_size > 0, f"Output file is empty: {filename}"


def test_regression_run_log_schema(tmp_path):
    """Verify that run_log.json has the expected schema."""
    result, folder = _make_context_and_run(tmp_path)

    run_log_path = folder / "run_log.json"
    assert run_log_path.exists(), "run_log.json not found"

    run_log = json.loads(run_log_path.read_text(encoding="utf-8"))

    # Top-level keys
    required_top_keys = [
        "run_id",
        "started_at",
        "finished_at",
        "model",
        "provider",
        "job",
        "steps",
        "totals",
        "package_folder",
        "files",
    ]
    for key in required_top_keys:
        assert key in run_log, f"run_log.json missing key: {key}"

    # Totals structure
    totals = run_log["totals"]
    assert "tokens_in" in totals
    assert "tokens_out" in totals
    assert "total_tokens" in totals

    # Steps is a list
    assert isinstance(run_log["steps"], list)
    assert len(run_log["steps"]) >= 8, f"Expected at least 8 steps, got {len(run_log['steps'])}"

    # Each step has required fields
    for step in run_log["steps"]:
        for field in ("name", "status", "started_at", "finished_at", "duration_seconds"):
            assert field in step, f"Step missing field '{field}': {step}"

    # files inventory is present
    assert isinstance(run_log["files"], dict)
    assert len(run_log["files"]) > 0


def test_regression_job_json_schema(tmp_path):
    """Verify that job.json has the expected fields."""
    result, folder = _make_context_and_run(tmp_path)

    job_json_path = folder / "job.json"
    assert job_json_path.exists(), "job.json not found"

    manifest = json.loads(job_json_path.read_text(encoding="utf-8"))

    # Required fields
    required_fields = [
        "id",
        "title",
        "company",
        "status",
        "source_url",
        "application_url",
        "date_added",
        "date_updated",
        "files",
    ]
    for field in required_fields:
        assert field in manifest, f"job.json missing field: {field}"

    # Verify values match what we passed in
    assert manifest["title"] == "Senior Software Engineer"
    assert manifest["company"] == "ExampleCorp"
    assert manifest["status"] == "reviewing"

    # files inventory
    files = manifest["files"]
    assert "resume_md" in files
    assert "resume_html" in files
    assert "resume_pdf" in files
    assert "fit_summary" in files


def test_regression_step_output_files(tmp_path):
    """Verify that each PipelineStep declares its expected output_file.

    Catches regressions where a step is silently dropped from the run_log's
    file inventory because output_file wasn't set.
    """
    result, _ = _make_context_and_run(tmp_path)

    step_outputs = {s.name: s.output_file for s in result.run.steps}

    expected = {
        "role_intel": "strategy.md",
        "resume_tailor": "resume.md",
        "format_resume": "resume.md",
        "positioning_brief": "positioning_brief.md",
        "cover_letter": "cover_letter.md",
        "email_inmail": "email_inmail.md",
        "fit_summary": "fit_summary.md",
    }
    for step_name, expected_file in expected.items():
        assert step_name in step_outputs, f"Step '{step_name}' missing"
        assert step_outputs[step_name] == expected_file, (
            f"Step '{step_name}' output_file mismatch: "
            f"got {step_outputs[step_name]!r}, expected {expected_file!r}"
        )


def test_regression_async_path_no_gate(tmp_path):
    """Pipeline runs to completion when on_gate is None (process-queue / async path).

    This is the code path used by `applycling process-queue` and OpenClaw
    integration. Must succeed without any interactive callback.
    """
    result, folder = _make_context_and_run(tmp_path, on_gate=None)

    assert folder.exists()
    assert (folder / "resume.md").exists()
    assert (folder / "fit_summary.md").exists()
    # Strategy was generated but not gated
    assert result.strategy and result.strategy.strip()


def test_regression_interactive_gate_override(tmp_path):
    """Pipeline invokes on_gate exactly once with strategy text and respects override.

    Verifies the interactive gate contract used by `applycling add` (without --async).
    """
    calls = []
    override_text = "## Overridden strategy\nUse this instead."

    def gate(content: str) -> str:
        calls.append(content)
        return override_text

    result, _ = _make_context_and_run(tmp_path, on_gate=gate)

    assert len(calls) == 1, f"Expected on_gate called once, got {len(calls)}"
    assert calls[0].strip(), "on_gate received empty strategy"
    assert result.strategy == override_text, (
        f"Expected override to replace strategy, got: {result.strategy!r}"
    )


def test_fixtures_exist():
    """Verify that all required fixtures are present."""
    required = ["job_description.txt", "base_resume.md", "profile.json"]
    for filename in required:
        path = FIXTURES_DIR / filename
        assert path.exists(), f"Missing fixture: {filename}"


def test_fixture_content():
    """Smoke test: fixtures have reasonable content."""
    jd = load_fixture("job_description.txt")
    assert "Senior Software Engineer" in jd
    assert len(jd) > 500

    resume = load_fixture("base_resume.md")
    assert "Jane Doe" in resume
    assert len(resume) > 300

    profile = json.loads(load_fixture("profile.json"))
    assert profile["name"] == "Jane Doe"
    assert profile["email"] == "jane.doe@example.com"
