"""Pipeline service layer for applycling.

This module provides the public contract for running applycling pipelines
programmatically. It's designed to be library-agnostic and work with
external orchestrators (e.g., OpenClaw) that invoke applycling as a
subprocess or service.

Key entities:
  - PipelineContext: immutable snapshot of user data, config, LLM settings
  - PipelineStep: a single atomic operation (e.g., role_intel, resume_tailor)
  - PipelineRun: result of running a full pipeline (e.g., add)
  - AddResult: output of the `add` pipeline with all artefacts
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json as _json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from . import llm, package, storage, tracker
from .skills import load_skill
from .text_utils import clean_llm_output as _clean_llm_output


def _utcnow() -> dt.datetime:
    """Naive UTC now via non-deprecated API.

    Returns a naive datetime so existing `.isoformat() + "Z"` serialization
    keeps working. Replaces `_utcnow()` (deprecated in 3.12+).
    """
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


@dataclass
class PipelineContext:
    """Immutable snapshot of user config, profile, and LLM settings.

    This is created once per pipeline run and passed to all steps.
    It encapsulates everything needed to make decisions and call LLMs.
    """

    # File system
    data_dir: Path
    output_dir: Path

    # User profile (loaded from data/profile.json)
    profile: dict[str, Any]

    # Base resume (never modified by LLM, loaded from data/resume.md)
    resume: str

    # Optional extra experiences (loaded from data/stories.md)
    stories: str

    # Optional LinkedIn profile (loaded from data/profile.json → linkedin_profile field)
    linkedin_profile: Optional[str]

    # Config (from data/config.json)
    config: dict[str, Any]

    # LLM settings (can override config)
    model: str
    provider: str

    # Tracker store for persisting jobs
    tracker_store: tracker.TrackerStore

    # Optional applicant profile (from data/applicant_profile.json)
    applicant_profile: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(
        cls,
        data_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> PipelineContext:
        """Load context from disk (data/ directory).

        Args:
            data_dir: Path to data directory (defaults to applycling/data)
            output_dir: Override output directory (defaults to config or ./output)
            model: Override LLM model
            provider: Override LLM provider

        Raises:
            storage.StorageError: If required files are missing.
        """
        # Load config, profile, resume, stories (uses global storage paths)
        config = storage.load_config()
        profile = storage.load_profile()
        resume = storage.load_resume()
        stories = storage.load_stories()

        # LinkedIn profile is optional
        try:
            linkedin_profile = storage.load_linkedin_profile()
        except storage.StorageError:
            linkedin_profile = None

        # Output directory
        output = output_dir or Path(config.get("output_dir", "./output")).expanduser()
        output.mkdir(parents=True, exist_ok=True)

        # LLM settings (with fallback to config)
        final_model = model or config.get("model")
        final_provider = provider or config.get("provider", "ollama")

        if not final_model:
            raise storage.StorageError("No model configured. Run setup first.")

        # Get tracker store
        store = tracker.get_store()

        applicant_profile = storage.load_applicant_profile()

        return cls(
            data_dir=Path(data_dir or storage.DATA_DIR),
            output_dir=output,
            profile=profile or {},
            resume=resume or "",
            stories=stories or "",
            linkedin_profile=linkedin_profile,
            applicant_profile=applicant_profile,
            config=config,
            model=final_model,
            provider=final_provider,
            tracker_store=store,
        )


@dataclass
class PipelineStep:
    """A single step in the pipeline that can be independently executed.

    This is the core abstraction that replaces _Step in cli.py. It tracks:
      - Timing (when it started/finished)
      - Output (collected via on_chunk callback)
      - Prompt (for debugging and token counting)
      - Status (ok/skipped/failed)

    Usage:
        step = PipelineStep("role_intel", output_file="strategy.md")
        step.prompt = prompt_text
        try:
            with step.streaming(on_chunk=lambda chunk: ...) as collector:
                for chunk in llm.role_intel(...):
                    collector(chunk)
        except Exception as e:
            step.mark_failed(e)
        result = step.output
    """

    name: str
    output_file: Optional[str] = None

    # Timing
    started_at: dt.datetime = field(default_factory=_utcnow)
    finished_at: Optional[dt.datetime] = None

    # Content
    prompt: str = ""
    output: str = ""
    status: str = "ok"  # "ok", "skipped", "failed"
    error: Optional[str] = None

    # Token accounting
    tokens_in: int = 0
    tokens_out: int = 0

    def duration_seconds(self) -> float:
        """Return duration in seconds, or 0 if not finished."""
        if self.finished_at is None:
            return 0.0
        delta = self.finished_at - self.started_at
        return round(delta.total_seconds(), 2)

    def mark_ok(self, output: str) -> None:
        """Mark step as successfully completed with output."""
        self.output = output
        self.status = "ok"
        self.finished_at = _utcnow()
        if not output.strip():
            self.status = "skipped"

    def mark_skipped(self) -> None:
        """Mark step as skipped (empty output)."""
        self.output = ""
        self.status = "skipped"
        self.finished_at = _utcnow()

    def mark_failed(self, error: Exception) -> None:
        """Mark step as failed."""
        self.status = "failed"
        self.error = str(error)
        self.finished_at = _utcnow()

    @contextmanager
    def streaming(
        self,
        on_chunk: Optional[OnChunkCallback] = None,
        on_status: Optional[OnStatusCallback] = None,
    ) -> Iterator[Callable[[str], None]]:
        """Context manager for streaming LLM output.

        Usage:
            step = PipelineStep("role_intel", output_file="strategy.md")
            step.prompt = prompt_text
            try:
                with step.streaming(on_chunk=lambda chunk: print(chunk, end="")) as collect:
                    for chunk in llm.role_intel(...):
                        collect(chunk)
            except Exception as e:
                step.mark_failed(e)
            result = step.output

        Args:
            on_chunk: Optional callback invoked for each chunk (for real-time streaming UI).
            on_status: Optional callback invoked when status changes (currently unused).

        Yields:
            A collector callable that appends chunks to self.output and calls on_chunk.
        """
        self.started_at = _utcnow()
        parts: list[str] = []

        def collect(chunk: str) -> None:
            parts.append(chunk)
            if on_chunk:
                on_chunk(chunk)

        try:
            yield collect
        finally:
            # Finalize on exit
            self.output = "".join(parts)
            self.finished_at = _utcnow()
            if not self.output.strip():
                self.status = "skipped"

    def to_dict(self) -> dict[str, Any]:
        """Convert to run_log format (without prompt/output for brevity)."""
        return {
            "name": self.name,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": (self.finished_at or _utcnow()).isoformat() + "Z",
            "duration_seconds": self.duration_seconds(),
            "output_file": self.output_file,
            "status": self.status,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            **({"error": self.error} if self.error else {}),
        }

    def to_dict_with_content(self) -> dict[str, Any]:
        """Convert to full format including prompt and output (for run_log)."""
        d = self.to_dict()
        d["prompt_text"] = self.prompt
        d["output_text"] = self.output
        return d


@dataclass
class PipelineRun:
    """Result of running a complete pipeline (e.g., applycling add).

    This aggregates all steps, timing, token counts, and cost estimates.
    """

    run_id: str
    started_at: dt.datetime
    finished_at: dt.datetime
    model: str
    provider: str
    steps: list[PipelineStep] = field(default_factory=list)

    # Job metadata
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    job_company: Optional[str] = None
    source_url: Optional[str] = None

    def duration_seconds(self) -> float:
        delta = self.finished_at - self.started_at
        return round(delta.total_seconds(), 2)

    def total_tokens(self) -> dict[str, int]:
        """Return total input/output/total tokens across all steps."""
        total_in = sum(s.tokens_in for s in self.steps)
        total_out = sum(s.tokens_out for s in self.steps)
        return {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "total_tokens": total_in + total_out,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to run_log JSON format."""
        totals = self.total_tokens()
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": self.finished_at.isoformat() + "Z",
            "duration_seconds": self.duration_seconds(),
            "model": self.model,
            "provider": self.provider,
            "job": {
                "id": self.job_id,
                "title": self.job_title,
                "company": self.job_company,
            },
            "source_url": self.source_url,
            "steps": [s.to_dict() for s in self.steps],
            "totals": totals,
        }


@dataclass
class AddResult:
    """Output of the `add` pipeline (tailoring a resume for a job).

    This is returned by `run_add()` and contains all generated artefacts
    as strings (not written to disk). The caller can persist via `persist()`.
    """

    run_id: str
    job: tracker.Job

    # Core artefacts
    resume_tailored: str
    fit_summary: str

    # Optional artefacts
    strategy: Optional[str] = None
    positioning_brief: Optional[str] = None
    cover_letter: Optional[str] = None
    email_inmail: Optional[str] = None
    job_description: Optional[str] = None
    company_context: Optional[str] = None

    # Pipeline run log
    run: PipelineRun = field(default_factory=lambda: PipelineRun(
        run_id="", started_at=_utcnow(), finished_at=_utcnow(),
        model="", provider=""
    ))

    # Job metadata (for convenience)
    job_title: str = ""
    job_company: str = ""

    def package_folder(self, output_root: Optional[Path] = None) -> str:
        """Return the canonical folder name for this result."""
        from . import package as pkg

        date = self.job.date_added.split("T")[0] if self.job.date_added else None
        return pkg.folder_name(
            self.job.company,
            self.job.title,
            date=date,
            job_id=self.job.id or None,
        )


# Callback types
OnChunkCallback = Callable[[str], None]
OnStatusCallback = Callable[[str], None]
OnGateCallback = Callable[[str], Optional[str]]  # Takes content, returns override or None


def compute_token_costs(
    steps: list[PipelineStep],
) -> tuple[dict[str, int], dict[str, float]]:
    """Compute token counts and cost estimates for a pipeline run.

    Uses tiktoken (cl100k_base encoding) for token counting, with fallbacks
    if tiktoken is unavailable.

    Args:
        steps: List of completed PipelineStep objects with prompt/output populated.

    Returns:
        (totals_dict, cost_estimates_dict) where:
          - totals_dict: {"tokens_in": int, "tokens_out": int, "total_tokens": int}
          - cost_estimates_dict: {model_name: estimated_cost_usd, ...}
    """
    cost_matrix = [
        ("gemini_2_flash", 0.10, 0.40),
        ("gpt4o_mini", 0.15, 0.60),
        ("claude_haiku", 0.80, 4.00),
        ("gpt4o", 2.50, 10.00),
        ("claude_sonnet", 3.00, 15.00),
        ("gemini_2_5_pro", 2.50, 15.00),
        ("claude_opus", 15.00, 75.00),
    ]

    total_in = 0
    total_out = 0

    # Try to use tiktoken for accurate token counts
    try:
        import tiktoken as _tiktoken

        _enc = _tiktoken.get_encoding("cl100k_base")
        for s in steps:
            _in = len(_enc.encode(s.prompt))
            _out = len(_enc.encode(s.output))
            s.tokens_in = _in
            s.tokens_out = _out
            total_in += _in
            total_out += _out
    except ImportError:
        # Fallback: estimate tokens as 1/4 of characters (rough heuristic)
        for s in steps:
            _in = len(s.prompt) // 4
            _out = len(s.output) // 4
            s.tokens_in = _in
            s.tokens_out = _out
            total_in += _in
            total_out += _out
    except Exception:
        # If anything goes wrong, skip token counting
        pass

    totals = {
        "tokens_in": total_in,
        "tokens_out": total_out,
        "total_tokens": total_in + total_out,
    }

    cost_estimates = {
        name: round((total_in * inp + total_out * out) / 1_000_000, 6)
        for name, inp, out in cost_matrix
    }

    return totals, cost_estimates


def _applicant_profile_block(profile: dict) -> str:
    """Serialize applicant profile dict to a key: value block for prompt injection."""
    labels = [
        ("work_auth", "Work authorization"),
        ("sponsorship_needed", "Sponsorship needed"),
        ("relocation", "Open to relocation"),
        ("relocation_cities", "Relocation cities"),
        ("remote_preference", "Remote preference"),
        ("comp_expectation", "Compensation expectations"),
        ("notice_period", "Notice period"),
        ("earliest_start_date", "Earliest start date"),
    ]
    lines = []
    for k, label in labels:
        v = profile.get(k)
        if v is None:
            continue
        if isinstance(v, bool):
            lines.append(f"{label}: {'yes' if v else 'no'}")
        elif isinstance(v, list):
            if v:  # skip empty lists
                lines.append(f"{label}: {', '.join(v)}")
        elif v:  # skip empty strings
            lines.append(f"{label}: {v}")
    return "\n".join(lines)


def _profile_header_markdown(profile: dict) -> str:
    """Build the static top section of the resume from stored profile fields."""
    lines = []
    name = profile.get("name", "").strip()
    if name:
        lines.append(f"# {name}\n")
    contact = " · ".join(filter(None, [
        profile.get("email", "").strip(),
        profile.get("phone", "").strip(),
        profile.get("location", "").strip(),
    ]))
    if contact:
        lines.append(contact)
    links = " · ".join(filter(None, [
        profile.get("linkedin", "").strip(),
        profile.get("github", "").strip(),
    ]))
    if links:
        lines.append(links)
    return "\n".join(lines)


def run_add(
    job_url: Optional[str],
    job_title: str,
    job_company: str,
    job_description: str,
    context: PipelineContext,
    *,
    company_url: Optional[str] = None,
    on_chunk: Optional[OnChunkCallback] = None,
    on_status: Optional[OnStatusCallback] = None,
    on_gate: Optional[OnGateCallback] = None,
    want_summary: bool = True,
    render_pdf: bool = True,
) -> AddResult:
    """Run the complete applycling add pipeline for a job.

    This is the core library function that replaces cli.add(). It handles all
    pipeline steps (role_intel, resume_tailor, etc.) and returns artefacts
    without persisting them. The caller is responsible for calling persist()
    if file I/O is desired.

    Args:
        job_url: Job posting URL (for source tracking).
        job_title: Job title.
        job_company: Company name.
        job_description: Full job description text.
        context: PipelineContext with user config, profile, LLM settings.
        company_url: Optional company page URL (for additional context).
        on_chunk: Optional callback for real-time streaming output.
        on_status: Optional callback for status updates.
        on_gate: Optional callback for interactive gates (strategy approval, etc.).
                 Takes the step content, returns override or None.
        want_summary: Whether to generate a profile summary (optional step).
        render_pdf: Whether to render HTML/PDF (True) or just keep .md (False).

    Returns:
        AddResult with all generated artefacts and pipeline metadata.

    Raises:
        llm.LLMError: If an LLM call fails critically.
        tracker.TrackerError: If job persistence fails.
    """
    run_id = str(uuid.uuid4())
    run_started = _utcnow()
    steps: list[PipelineStep] = []

    # Fetch company page text (optional, no LLM call).
    company_page_text = ""
    if company_url:
        try:
            from . import scraper as _scraper
            company_page_text = _scraper.fetch_page_text(company_url)
        except Exception:
            pass  # Non-critical; continue without company context.

    # Log company context as a pipeline step so it appears in run_log.
    if company_url:
        _ctx_step = PipelineStep("company_context", output_file="company_context.md")
        _ctx_step.prompt = company_url
        _ctx_step.mark_ok(company_page_text)
        steps.append(_ctx_step)

    # ---- Step 1: Role Intel (single merged pass) ----
    if on_status:
        on_status("Running role intel...")

    _co_note = "\nUse the company page text below to inform this section." if company_page_text else ""
    _cand_section = "\nYou have the candidate's base resume below. Use it to assess keyword coverage and gaps."
    _intel_prompt = load_skill("role_intel").render(
        job_description=job_description, company_note=_co_note, candidate_section=_cand_section
    )
    if company_page_text:
        _intel_prompt += f"\n\n=== COMPANY PAGE TEXT ===\n{company_page_text}\n"
    _intel_prompt += f"\n\n=== CANDIDATE BASE RESUME ===\n{context.resume}\n"

    step = PipelineStep("role_intel", output_file="strategy.md")
    step.prompt = _intel_prompt
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.role_intel(
                job_description, context.model,
                company_page_text=company_page_text or None,
                resume=context.resume,
                provider=context.provider,
            ):
                collect(chunk)
    except llm.LLMError as e:
        step.mark_failed(e)
        raise
    steps.append(step)
    strategy = _clean_llm_output(step.output)

    # Interactive gate: review strategy and optionally override.
    if on_gate:
        override = on_gate(strategy)
        if override:
            strategy = override

    # ---- Step 2: Resume Tailor ----
    if on_status:
        on_status("Tailoring resume...")

    _stories_section = (
        "\n- You have been given CANDIDATE STORIES below. "
        "Draw from these only when they genuinely strengthen this application for this specific role. "
        "Omit anything that isn't relevant."
    ) if context.stories else ""
    _vt = f" Candidate's voice and tone: {context.profile['voice_tone']}" if context.profile and context.profile.get("voice_tone") else ""
    _nf_list = context.profile.get("never_fabricate", []) if context.profile else []
    _nf = f"\n- Specifically NEVER fabricate: {'; '.join(_nf_list)}." if _nf_list else ""
    _tailor_prompt = load_skill("resume_tailor").render(
        resume=context.resume, job_description=job_description,
        stories_section=_stories_section, voice_tone_section=_vt,
        never_fabricate_section=_nf,
    )
    if strategy:
        _tailor_prompt += f"\n\n=== POSITIONING STRATEGY (follow this closely) ===\n{strategy}\n"
    if context.stories:
        _tailor_prompt += f"\n\n=== CANDIDATE STORIES (draw from when relevant) ===\n{context.stories}\n"
    if context.linkedin_profile:
        _tailor_prompt += f"\n\n=== LINKEDIN PROFILE (draw from when relevant) ===\n{context.linkedin_profile}\n"

    step = PipelineStep("resume_tailor", output_file="resume.md")
    step.prompt = _tailor_prompt
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.tailor_resume(
                context.resume, job_description, context.model,
                stories=context.stories, strategy=strategy,
                voice_tone=context.profile.get("voice_tone") if context.profile else None,
                never_fabricate=context.profile.get("never_fabricate") if context.profile else None,
                linkedin_profile=context.linkedin_profile,
                provider=context.provider,
            ):
                collect(chunk)
    except llm.LLMError as e:
        step.mark_failed(e)
        raise
    steps.append(step)
    tailored_body = _clean_llm_output(step.output)

    # ---- Step 3: Profile Summary (optional) ----
    profile_summary = ""
    if want_summary:
        if on_status:
            on_status("Generating profile summary...")

        step = PipelineStep("profile_summary")
        step.prompt = load_skill("profile_summary").render(
            resume=context.resume, job_description=job_description
        )
        try:
            with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
                for chunk in llm.get_profile_summary(
                    context.resume, job_description, context.model, provider=context.provider
                ):
                    collect(chunk)
        except llm.LLMError:
            # Non-critical step; skip on failure
            step.mark_skipped()
        steps.append(step)
        profile_summary = _clean_llm_output(step.output)

    # ---- Step 4: Format pass (reshape to preferred template) ----
    if on_status:
        on_status("Formatting resume...")

    step = PipelineStep("format_resume", output_file="resume.md")
    step.prompt = load_skill("format_resume").render(resume=tailored_body)
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.format_resume(tailored_body, context.model, provider=context.provider):
                collect(chunk)
    except llm.LLMError:
        # Non-critical; use unformatted output
        step.mark_skipped()
    steps.append(step)
    formatted_body = _clean_llm_output(step.output) or tailored_body

    # Assemble final resume: static profile header + optional summary + formatted body.
    resume_sections = []
    if context.profile:
        resume_sections.append(_profile_header_markdown(context.profile))
    if profile_summary:
        resume_sections.append(f"## PROFILE\n\n{profile_summary}")
    resume_sections.append(formatted_body)
    tailored = "\n\n".join(resume_sections)

    # ---- Step 5: Positioning Brief ----
    if on_status:
        on_status("Generating positioning brief...")

    step = PipelineStep("positioning_brief", output_file="positioning_brief.md")
    step.prompt = load_skill("positioning_brief").render(
        role_intel=strategy, tailored_resume=tailored, job_description=job_description
    )
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.positioning_brief(
                strategy, tailored, job_description, context.model, provider=context.provider
            ):
                collect(chunk)
    except llm.LLMError as e:
        step.mark_failed(e)
        raise
    steps.append(step)
    pos_brief = _clean_llm_output(step.output)

    # ---- Step 6: Cover Letter ----
    if on_status:
        on_status("Writing cover letter...")

    _vt = f" Candidate's voice and tone: {context.profile['voice_tone']}" if context.profile and context.profile.get("voice_tone") else ""
    _ap_section = (
        f"\n=== APPLICANT PROFILE ===\n{_applicant_profile_block(context.applicant_profile)}"
        if context.applicant_profile else ""
    )
    step = PipelineStep("cover_letter", output_file="cover_letter.md")
    step.prompt = load_skill("cover_letter").render(
        role_intel=strategy, tailored_resume=tailored,
        job_description=job_description, voice_tone_section=_vt,
        applicant_profile_section=_ap_section,
    )
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.cover_letter(
                strategy, tailored, job_description, context.model,
                voice_tone=context.profile.get("voice_tone") if context.profile else None,
                provider=context.provider,
                applicant_profile_section=_ap_section,
            ):
                collect(chunk)
    except llm.LLMError:
        # Non-critical
        step.mark_skipped()
    steps.append(step)
    cover_letter_text = _clean_llm_output(step.output)

    # ---- Step 7: Email / InMail ----
    if on_status:
        on_status("Drafting email and InMail...")

    email_inmail_text = ""
    if context.profile:
        contact_line = " · ".join(filter(None, [
            context.profile.get("email", ""),
            context.profile.get("phone", ""),
        ]))
        _vt = f" Candidate's voice and tone: {context.profile['voice_tone']}" if context.profile.get("voice_tone") else ""
        step = PipelineStep("email_inmail", output_file="email_inmail.md")
        step.prompt = load_skill("email_inmail").render(
            role_intel=strategy, candidate_name=context.profile.get("name", ""),
            candidate_contact=contact_line, job_title=job_title,
            company=job_company, voice_tone_section=_vt,
            applicant_profile_section=_ap_section,
        )
        try:
            with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
                for chunk in llm.application_email(
                    strategy, context.profile.get("name", ""), contact_line,
                    job_title, job_company, context.model,
                    voice_tone=context.profile.get("voice_tone"),
                    provider=context.provider,
                    applicant_profile_section=_ap_section,
                ):
                    collect(chunk)
        except llm.LLMError:
            # Non-critical
            step.mark_skipped()
        steps.append(step)
        email_inmail_text = _clean_llm_output(step.output)

    # ---- Step 8: Fit Summary ----
    if on_status:
        on_status("Generating fit summary...")

    step = PipelineStep("fit_summary", output_file="fit_summary.md")
    step.prompt = load_skill("fit_summary").render(
        resume=context.resume, job_description=job_description
    )
    try:
        with step.streaming(on_chunk=on_chunk, on_status=on_status) as collect:
            for chunk in llm.get_fit_summary(
                context.resume, job_description, context.model, provider=context.provider
            ):
                collect(chunk)
    except llm.LLMError as e:
        step.mark_failed(e)
        raise
    steps.append(step)
    fit_summary = _clean_llm_output(step.output)

    # ---- Finalize run log ----
    run_finished = _utcnow()
    run_log = PipelineRun(
        run_id=run_id,
        started_at=run_started,
        finished_at=run_finished,
        model=context.model,
        provider=context.provider,
        steps=steps,
        job_title=job_title,
        job_company=job_company,
        source_url=job_url,
    )

    # Compute token costs
    totals, cost_estimates = compute_token_costs(steps)

    # Persist job to tracker
    job = tracker.Job(
        id="",
        title=job_title,
        company=job_company,
        date_added="",
        date_updated="",
        status="tailored",
        source_url=job_url or None,
        fit_summary=fit_summary or None,
    )
    job = context.tracker_store.save_job(job)
    run_log.job_id = job.id

    # Build result
    return AddResult(
        run_id=run_id,
        job=job,
        resume_tailored=tailored,
        fit_summary=fit_summary,
        strategy=strategy,
        positioning_brief=pos_brief,
        cover_letter=cover_letter_text,
        email_inmail=email_inmail_text,
        job_description=job_description,
        company_context=company_page_text,
        run=run_log,
        job_title=job_title,
        job_company=job_company,
    )


def load_run_log(package_folder: Path) -> Optional[dict[str, Any]]:
    """Load run_log.json from a package folder.

    Args:
        package_folder: Path to the package folder containing run_log.json.

    Returns:
        The parsed run_log dict, or None if the file doesn't exist.
    """
    run_log_path = package_folder / "run_log.json"
    if not run_log_path.exists():
        return None

    import json as _json
    return _json.loads(run_log_path.read_text(encoding="utf-8"))


def load_package_artifacts(package_folder: Path) -> dict[str, str]:
    """Load all markdown artifacts from a package folder.

    Args:
        package_folder: Path to the package folder.

    Returns:
        Dict of artifact names to their text content:
          - "resume": resume.md
          - "strategy": strategy.md
          - "positioning_brief": positioning_brief.md
          - "cover_letter": cover_letter.md
          - "email_inmail": email_inmail.md
          - "job_description": job_description.md
    """
    artifacts = {}
    artifact_files = {
        "resume": "resume.md",
        "strategy": "strategy.md",
        "positioning_brief": "positioning_brief.md",
        "cover_letter": "cover_letter.md",
        "email_inmail": "email_inmail.md",
        "job_description": "job_description.md",
        "fit_summary": "fit_summary.md",
        "company_context": "company_context.md",
    }

    for name, filename in artifact_files.items():
        path = package_folder / filename
        if path.exists():
            artifacts[name] = path.read_text(encoding="utf-8")

    return artifacts


def answer_questions(
    job_id: str,
    questions: str,
    ctx: PipelineContext,
) -> str:
    """Draft answers to application form questions for a job.

    Args:
        job_id: Job ID to load from the tracker.
        questions: Form questions text (caller may append feedback for refine iterations).
        ctx: PipelineContext supplying LLM settings, resume, stories, and applicant_profile.

    Returns:
        Drafted answers as a cleaned string.

    Raises:
        tracker.TrackerError: If job_id is not found.
        ValueError: If job has no package folder recorded.
        llm.LLMError: If the LLM call fails.
    """
    job = ctx.tracker_store.load_job(job_id)

    if not job.package_folder:
        raise ValueError(f"Job {job_id} has no package folder. Run 'applycling add' first.")

    folder = Path(job.package_folder)
    if not folder.exists():
        raise ValueError(f"Package folder not found on disk: {folder}")

    artifacts = load_package_artifacts(folder)
    if not artifacts.get("resume"):
        raise ValueError(f"Package folder is missing resume.md — folder may be incomplete: {folder}")
    ap_block = _applicant_profile_block(ctx.applicant_profile) if ctx.applicant_profile else ""

    parts: list[str] = []
    for chunk in llm.answer_questions(
        resume=artifacts.get("resume", ctx.resume),
        stories=ctx.stories,
        role_intel=artifacts.get("strategy", ""),
        company_context=artifacts.get("company_context", ""),
        positioning_brief=artifacts.get("positioning_brief", ""),
        applicant_profile=ap_block,
        questions=questions,
        model=ctx.model,
        provider=ctx.provider,
    ):
        parts.append(chunk)

    return _clean_llm_output("".join(parts))


def get_step_names_before_checkpoint(checkpoint: str) -> list[str]:
    """Return list of step names that should be skipped when resuming from a checkpoint.

    Steps are executed in order:
      1. role_intel
      2. resume_tailor
      3. profile_summary
      4. format_resume
      5. positioning_brief
      6. cover_letter
      7. email_inmail
      8. fit_summary

    If checkpoint is "positioning_brief", we skip steps 1-4 and resume from step 5.

    Args:
        checkpoint: Step name to resume from (inclusive).

    Returns:
        List of step names to skip.
    """
    all_steps = [
        "role_intel",
        "resume_tailor",
        "profile_summary",
        "format_resume",
        "positioning_brief",
        "cover_letter",
        "email_inmail",
        "fit_summary",
    ]

    try:
        checkpoint_idx = all_steps.index(checkpoint)
        return all_steps[:checkpoint_idx]  # Skip all steps before the checkpoint
    except ValueError:
        raise ValueError(f"Unknown checkpoint: {checkpoint}")


def persist_add_result(
    result: AddResult,
    output_root: Optional[Path] = None,
    generate_docx: bool = False,
    generate_run_log: bool = True,
) -> Path:
    """Write an AddResult to disk as a package folder.

    This separates I/O from computation, making the library testable.

    Args:
        result: The AddResult from run_add().
        output_root: Output directory (defaults to ./output).
        generate_docx: Whether to generate .docx files.
        generate_run_log: Whether to write run_log.json.

    Returns:
        Path to the generated package folder.
    """
    # Build run_log dict
    run_dict = result.run.to_dict()
    totals, cost_estimates = compute_token_costs(result.run.steps)
    run_dict["totals"] = totals
    run_dict["cost_estimates"] = cost_estimates

    # Call package assembler
    folder = package.assemble(
        result.job,
        result.resume_tailored,
        result.fit_summary,
        output_root=output_root,
        strategy=result.strategy,
        company_context=result.company_context,
        positioning_brief=result.positioning_brief,
        cover_letter=result.cover_letter,
        email_inmail=result.email_inmail,
        job_description=result.job_description,
        generate_docx=generate_docx,
        run_log=run_dict if generate_run_log else None,
    )

    # Update job with package folder
    result.job = dataclasses.replace(result.job, package_folder=str(folder))

    return folder


def run_add_notify(
    url: str,
    notifier: "Any",
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    output_root: Optional[Path] = None,
) -> Path:
    """Run the full add pipeline and deliver results via any Notifier.

    This is the channel-agnostic worker. It scrapes the URL, runs the pipeline,
    persists artefacts, sends PDFs, and sends a completion summary — all via the
    notifier's ``notify`` / ``send_document`` interface.

    Args:
        url: Job posting URL to scrape and process.
        notifier: Any object satisfying the Notifier protocol (TelegramNotifier,
                  DiscordNotifier, etc.).
        model: Override LLM model from config.
        provider: Override LLM provider from config.
        output_root: Override output directory.

    Returns:
        Path to the assembled package folder.
    """
    from . import scraper, storage, tracker

    def _safe(text: str) -> None:
        try:
            notifier.notify(text)
        except Exception:
            pass

    # Load config
    cfg = storage.load_config()
    final_model = model or cfg.get("model")
    final_provider = provider or cfg.get("provider", "ollama")
    out_root = output_root or (Path(cfg.get("output_dir", "./output")).expanduser())

    _safe(f"⚙️ Queued: {url}\nProcessing will begin shortly…")

    # Scrape
    _safe("📄 Scraping job description…")
    try:
        posting, _ = scraper.fetch_job_posting(url, final_model, provider=final_provider)
    except Exception as e:
        _safe(f"❌ Failed to scrape job URL.\nError: {e}")
        raise

    title, company = posting.title, posting.company
    _safe(f"✅ Fetched: {title} @ {company}")

    # Build context
    profile = storage.load_profile() or {}
    stories = storage.load_stories() or ""
    linkedin_profile = storage.load_linkedin_profile() if cfg.get("use_linkedin_profile", True) else None
    applicant_profile = storage.load_applicant_profile()

    ctx = PipelineContext(
        data_dir=storage.DATA_DIR,
        output_dir=out_root,
        profile=profile,
        resume=storage.load_resume(),
        stories=stories,
        linkedin_profile=linkedin_profile,
        applicant_profile=applicant_profile,
        config=cfg,
        model=final_model,
        provider=final_provider,
        tracker_store=tracker.get_store(),
    )

    _STATUS_MAP = {
        "Running role intel": "🎯 Analysing role…",
        "Tailoring resume": "✍️ Tailoring resume…",
        "Generating profile summary": "👤 Writing profile summary…",
        "Formatting resume": "📝 Formatting resume…",
        "Generating positioning brief": "🗺️ Positioning brief…",
        "Writing cover letter": "💌 Writing cover letter…",
        "Drafting email and InMail": "📧 Drafting email…",
        "Generating fit summary": "📊 Fit summary…",
    }

    def _on_status(msg: str) -> None:
        for key, emoji_msg in _STATUS_MAP.items():
            if key.lower() in msg.lower():
                _safe(emoji_msg)
                return

    # Run pipeline
    try:
        result = run_add(
            job_url=url,
            job_title=title,
            job_company=company,
            job_description=posting.description,
            context=ctx,
            company_url=posting.company_url or None,
            on_status=_on_status,
            on_gate=None,
            want_summary=True,
            render_pdf=True,
        )
    except llm.LLMError as e:
        _safe(f"❌ Pipeline failed.\nError: {e}")
        raise

    # Persist
    _safe("📦 Assembling package…")
    try:
        folder = persist_add_result(
            result,
            output_root=out_root,
            generate_docx=cfg.get("generate_docx", False),
            generate_run_log=cfg.get("generate_run_log", True),
        )
        try:
            ctx.tracker_store.update_job(result.job.id, package_folder=str(folder))
        except Exception:
            pass
    except Exception as e:
        _safe(f"❌ Package assembly failed.\nError: {e}")
        raise

    # Send documents
    for pdf_name, caption in [
        ("resume.pdf", f"Resume — {title} @ {company}"),
        ("cover_letter.pdf", f"Cover Letter — {title} @ {company}"),
    ]:
        pdf_path = folder / pdf_name
        if pdf_path.exists():
            try:
                notifier.send_document(pdf_path, caption=caption)
            except Exception as e:
                _safe(f"⚠️ Could not send {pdf_name}: {e}")

    # Completion summary
    fit = (result.fit_summary or "").strip()
    lines = [
        f"✅ Done! {title} @ {company}",
        f"Job ID: {result.job.id}",
        f"📁 {folder}",
    ]
    if fit:
        lines.append(f"\n📊 Fit summary:\n{fit}")

    # Notion DB link if configured
    try:
        notion_path = storage.DATA_DIR / "notion.json"
        if notion_path.exists():
            import json as _json
            nc = _json.loads(notion_path.read_text(encoding="utf-8"))
            db_id = nc.get("database_id", "")
            if db_id:
                lines.append(f"\n🔗 Notion: https://notion.so/{db_id.replace('-', '')}")
    except Exception:
        pass

    _safe("\n".join(lines))
    return folder
