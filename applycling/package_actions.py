"""Reusable package-action helpers — shared by CLI and MCP.

This module contains the domain logic for post-package actions (interview
prep and refinement). It has NO UI dependencies — no click, rich, Prompt,
Panel, or console. CLI wrappers in applycling/cli.py handle user interaction
and display; MCP tools call these helpers and return structured dicts.

Architecture:
    CLI ┐
        ├─> applycling.package_actions -> tracker/storage/llm/render/skills
    MCP ┘
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigurationError(RuntimeError):
    """Raised when package actions cannot run because config/model is missing."""


# ---------------------------------------------------------------------------
# Constants shared by CLI and MCP
# ---------------------------------------------------------------------------

_ARTIFACT_ALIASES: dict[str, str] = {
    "resume": "resume",
    "cover-letter": "cover_letter",
    "coverletter": "cover_letter",
    "cl": "cover_letter",
    "brief": "brief",
    "positioning-brief": "brief",
    "email": "email",
    "inmail": "email",
    "email-inmail": "email",
}

# Downstream cascade: regenerating X also regenerates these (in order).
_DOWNSTREAM: dict[str, list[str]] = {
    "resume": ["brief", "cover_letter", "email"],
    "cover_letter": ["email"],
    "brief": [],
    "email": [],
}

_VERSIONABLE = {
    "resume.md", "resume.html", "resume.pdf", "resume.docx",
    "cover_letter.md", "cover_letter.html", "cover_letter.pdf", "cover_letter.docx",
    "positioning_brief.md", "email_inmail.md",
}

_PREP_STAGES = ("recruiter", "hiring-manager", "technical", "executive")

_PREP_STAGE_LABELS = {
    "recruiter": "recruiter screen",
    "hiring-manager": "hiring manager deep-dive",
    "technical": "technical",
    "executive": "executive",
}

_INTEL_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
_INTEL_TEXT_EXTS = {".md", ".txt", ".text"}


# ---------------------------------------------------------------------------
# Small helpers (moved from cli.py)
# ---------------------------------------------------------------------------


def _parse_refine_only(only_str: str) -> list[str]:
    """Parse a comma-separated artifact list into canonical names."""
    if not only_str.strip():
        return []
    result = []
    for part in only_str.split(","):
        key = part.strip().lower()
        canonical = _ARTIFACT_ALIASES.get(key)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _version_artifacts(folder: Path) -> Path:
    """Copy all versionable root files into a v{n}/ snapshot folder."""
    import shutil

    existing = sorted(
        int(d.name[1:]) for d in folder.iterdir()
        if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
    )
    next_v = (existing[-1] + 1) if existing else 1
    v_folder = folder / f"v{next_v}"
    v_folder.mkdir()
    for fname in _VERSIONABLE:
        src = folder / fname
        if src.exists():
            shutil.copy2(src, v_folder / fname)
    return v_folder


def _read_intel_folder(
    folder: Path,
    vision_model: str = "",
    vision_provider: str = "",
) -> tuple[str, list[str]]:
    """Read all files from intel/ subfolder.

    Returns (combined_text, warnings). Warnings are shown for unreadable
    or unsupported files. If vision_model is set, image files are processed
    via the vision LLM. Extraction caches live in intel/.cache/.
    """
    from applycling import llm

    intel_dir = folder / "intel"
    if not intel_dir.exists():
        return "", []

    cache_dir = intel_dir / ".cache"
    parts: list[str] = []
    warnings: list[str] = []

    for f in sorted(intel_dir.iterdir()):
        if f.is_dir():
            continue
        ext = f.suffix.lower()

        if ext in _INTEL_IMAGE_EXTS:
            cache_path = cache_dir / f"{f.stem}.extracted.md"
            old_cache_path = intel_dir / f"{f.stem}.extracted.md"
            if not cache_path.exists() and old_cache_path.exists():
                cache_dir.mkdir(exist_ok=True)
                cache_path.write_text(old_cache_path.read_text(encoding="utf-8"), encoding="utf-8")
                old_cache_path.unlink()

            if cache_path.exists() and cache_path.stat().st_mtime >= f.stat().st_mtime:
                try:
                    cached = cache_path.read_text(encoding="utf-8").strip()
                    if cached:
                        parts.append(f"--- {f.name} (cached) ---\n{cached}")
                        continue
                except Exception:
                    pass

            if vision_model:
                try:
                    text = llm.extract_image_text(f, vision_model, vision_provider)
                    if text.strip():
                        parts.append(f"--- {f.name} (extracted via {vision_model}) ---\n{text.strip()}")
                        cache_dir.mkdir(exist_ok=True)
                        cache_path.write_text(text.strip(), encoding="utf-8")
                    else:
                        warnings.append(f"{f.name}: vision model returned empty text.")
                except llm.LLMError as e:
                    warnings.append(f"{f.name}: vision extraction failed ({e}).")
            else:
                warnings.append(
                    f"{f.name}: image file skipped — set intel_vision_model and "
                    f"intel_vision_provider in data/config.json to enable image extraction."
                )
        elif ext == ".pdf":
            try:
                from applycling import pdf_import
                text = pdf_import.extract_text(f)
                if text.strip():
                    parts.append(f"--- {f.name} ---\n{text.strip()}")
                elif vision_model:
                    warnings.append(
                        f"{f.name}: PDF appears to be image-only. "
                        f"Vision extraction for PDFs is not yet supported."
                    )
                else:
                    warnings.append(f"{f.name}: PDF extracted but appears to be empty or image-only.")
            except Exception as e:
                warnings.append(f"{f.name}: could not read PDF ({e}).")
        elif ext in _INTEL_TEXT_EXTS:
            try:
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"--- {f.name} ---\n{text}")
                else:
                    warnings.append(f"{f.name}: file is empty.")
            except Exception as e:
                warnings.append(f"{f.name}: could not read file ({e}).")
        else:
            warnings.append(f"{f.name}: unsupported file type ({ext}).")

    return "\n\n".join(parts), warnings


# ---------------------------------------------------------------------------
# Config / model resolution (MCP-safe — no sys.exit)
# ---------------------------------------------------------------------------


def _load_config_safe() -> dict:
    """Load applycling config dict. Raises ConfigurationError if missing."""
    from applycling.storage import load_config, StorageError

    try:
        return load_config()
    except StorageError:
        raise ConfigurationError("No config found. Run applycling setup first.")


def _resolve_model_provider(
    cfg: dict,
    model: str | None,
    provider: str | None,
) -> tuple[str, str]:
    """Resolve effective model and provider from config + overrides.

    Raises ConfigurationError if neither config nor override provides a model.
    """
    effective_model = model or cfg.get("model", "")
    effective_provider = provider or cfg.get("provider", "ollama")
    if not effective_model:
        raise ConfigurationError("No model in config. Run applycling setup first.")
    return effective_model, effective_provider


# ---------------------------------------------------------------------------
# Package validation
# ---------------------------------------------------------------------------


def _validate_package_files(folder: Path) -> tuple[str, str, str, str]:
    """Validate required package files exist. Returns (resume, jd, strategy, brief).

    Raises FileNotFoundError on missing resume or job description.
    """
    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    resume = _read("resume.md")
    strategy = _read("strategy.md")
    positioning_brief = _read("positioning_brief.md")
    job_description = _read("job_description.md") or strategy

    if not resume:
        raise FileNotFoundError(f"resume.md not found in {folder}")
    if not job_description:
        raise FileNotFoundError(f"No job_description.md or strategy.md found in {folder}")

    return resume, job_description, strategy, positioning_brief


# ---------------------------------------------------------------------------
# Main helper API
# ---------------------------------------------------------------------------


def generate_interview_prep_for_job(
    job_id: str,
    *,
    stage: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Generate interview_prep.md for a package and return metadata."""
    from applycling.tracker import get_store, TrackerError
    from applycling.skills.loader import load_skill
    from applycling import llm
    from applycling.text_utils import clean_llm_output

    # Load job + validate package FIRST — so missing-job errors are
    # deterministic regardless of config state.
    job = get_store().load_job(job_id)

    if not job.package_folder:
        raise ValueError("No package folder recorded for this job.")
    folder = Path(job.package_folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Package folder not found: {folder}")

    # Config/model resolution after job validation — so missing-job errors surface first.
    cfg = _load_config_safe()
    eff_model, eff_provider = _resolve_model_provider(cfg, model, provider)

    # Validate stage
    if stage is not None and stage not in _PREP_STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Valid: {', '.join(_PREP_STAGES)}")

    # Resolve stage labels
    if stage is not None:
        stages_str = _PREP_STAGE_LABELS[stage]
    else:
        stages_str = ", ".join(_PREP_STAGE_LABELS.values())

    resume, job_description, strategy, positioning_brief_text = _validate_package_files(folder)

    # Intel collection
    vision_model = cfg.get("intel_vision_model", "")
    vision_provider = cfg.get("intel_vision_provider", eff_provider) if vision_model else ""
    intel_folder_text, _intel_warnings = _read_intel_folder(
        folder, vision_model=vision_model, vision_provider=vision_provider,
    )

    store = get_store()
    notion_notes = store.load_job_notes(job_id)

    intel_parts: list[str] = []
    if intel_folder_text:
        intel_parts.append(intel_folder_text)
    if notion_notes:
        intel_parts.append(f"--- Notion page notes ---\n{notion_notes}")
    intel_combined = "\n\n".join(intel_parts)

    # Generate
    prompt_text = load_skill("interview_prep").render(
        stages=stages_str,
        job_description=job_description,
        resume=resume,
        role_intel=strategy,
        positioning_brief=positioning_brief_text or "(not provided)",
        intel_section=f"\n=== ADDITIONAL INTEL ===\n{intel_combined}\n" if intel_combined else "",
    )

    chunks: list[str] = []
    try:
        for chunk in llm.interview_prep(
            job_description, resume, strategy, eff_model,
            positioning_brief=positioning_brief_text,
            intel=intel_combined,
            stages=stages_str,
            provider=eff_provider,
        ):
            chunks.append(chunk)
    except llm.LLMError as e:
        raise RuntimeError(f"LLM interview_prep failed: {e}") from e

    prep_text = clean_llm_output("".join(chunks))
    if not prep_text:
        raise RuntimeError("Prep came back empty.")

    out_path = folder / "interview_prep.md"
    out_path.write_text(
        f"# Interview Prep — {job.title} @ {job.company}\n\n{prep_text}\n",
        encoding="utf-8",
    )

    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "package_folder": str(folder),
        "artifacts": [
            {"name": "interview_prep.md", "path": str(out_path), "kind": "interview_prep"}
        ],
        "status": "complete",
    }


def refine_package_for_job(
    job_id: str,
    *,
    feedback: str,
    artifacts: list[str] | None = None,
    cascade: bool = False,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Refine selected package artifacts and return changed paths."""
    from applycling.tracker import get_store
    from applycling.skills.loader import load_skill
    from applycling import llm, render
    from applycling.text_utils import clean_llm_output

    if not feedback.strip():
        raise ValueError("Feedback is required for refinement.")

    # Load job + validate package BEFORE config — so missing-job errors surface first.
    job = get_store().load_job(job_id)

    if not job.package_folder:
        raise ValueError("No package folder recorded for this job.")
    folder = Path(job.package_folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Package folder not found: {folder}")

    cfg = _load_config_safe()
    eff_model, eff_provider = _resolve_model_provider(cfg, model, provider)

    resume, job_description, strategy, _brief = _validate_package_files(folder)

    # Load existing artifacts
    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    existing_cover_letter = _read("cover_letter.md")
    existing_brief = _read("positioning_brief.md")
    existing_email = _read("email_inmail.md")

    # Determine which artifacts to refine
    if artifacts is not None:
        explicit = _parse_refine_only(", ".join(artifacts))
    else:
        explicit: list[str] = []
        if resume:
            explicit.append("resume")
        if existing_cover_letter:
            explicit.append("cover_letter")
        if existing_brief:
            explicit.append("brief")
        if existing_email:
            explicit.append("email")

    if not explicit:
        raise ValueError("No artifacts found to refine.")

    # Apply cascade
    in_scope: list[str] = list(explicit)
    if artifacts is None or cascade:
        for artifact in list(explicit):
            for downstream in _DOWNSTREAM.get(artifact, []):
                if downstream not in in_scope:
                    fname_map = {
                        "cover_letter": "cover_letter.md",
                        "brief": "positioning_brief.md",
                        "email": "email_inmail.md",
                    }
                    if (folder / fname_map.get(downstream, f"{downstream}.md")).exists():
                        in_scope.append(downstream)

    # Snapshot existing files
    v_folder = _version_artifacts(folder)
    changed_paths: list[str] = []

    # --- Refine resume ---
    if "resume" in in_scope:
        chunks: list[str] = []
        try:
            for chunk in llm.refine_resume(resume, job_description, feedback, eff_model, provider=eff_provider):
                chunks.append(chunk)
        except llm.LLMError as e:
            raise RuntimeError(f"LLM refine_resume failed: {e}") from e
        refined_body = clean_llm_output("".join(chunks))

        # Format pass
        fmt_chunks: list[str] = []
        try:
            for chunk in llm.format_resume(refined_body, eff_model, provider=eff_provider):
                fmt_chunks.append(chunk)
        except llm.LLMError:
            pass  # Use unformatted output
        formatted_body = clean_llm_output("".join(fmt_chunks)) or refined_body

        # Profile header assembly
        import re
        from applycling.storage import load_profile
        from applycling.pipeline import _profile_header_markdown

        profile = load_profile()
        sections: list[str] = []
        if profile:
            sections.append(_profile_header_markdown(profile))
        profile_match = re.search(r"## PROFILE\s*\n(.*?)(?=\n## |\Z)", resume, flags=re.DOTALL)
        if profile_match:
            profile_text = profile_match.group(1).strip()
            sections.append(f"## PROFILE\n\n{profile_text}")
        sections.append(formatted_body)
        refined_resume_full = "\n\n".join(sections)

        (folder / "resume.md").write_text(refined_resume_full, encoding="utf-8")
        changed_paths.append("resume.md")

        # Re-render
        try:
            render.render_resume(refined_resume_full, folder, title=f"{job.title} — {job.company}")
            changed_paths.append("resume.html")
            changed_paths.append("resume.pdf")
            if cfg.get("generate_docx", False):
                render.markdown_to_docx(refined_resume_full, folder / "resume.docx")
                changed_paths.append("resume.docx")
        except Exception:
            pass  # Render is best-effort; markdown is the source of truth

    # --- Refine positioning brief ---
    if "brief" in in_scope and existing_brief:
        current_resume = _read("resume.md")  # re-read after possible refinement
        chunks: list[str] = []
        try:
            for chunk in llm.refine_positioning_brief(
                existing_brief, current_resume, strategy, feedback, eff_model, provider=eff_provider
            ):
                chunks.append(chunk)
        except llm.LLMError:
            pass  # Brief is non-critical
        if chunks:
            refined_brief = clean_llm_output("".join(chunks))
            if refined_brief.strip():
                (folder / "positioning_brief.md").write_text(
                    f"# Positioning brief — {job.title} @ {job.company}\n\n{refined_brief}\n",
                    encoding="utf-8",
                )
                changed_paths.append("positioning_brief.md")

    # --- Refine cover letter ---
    if "cover_letter" in in_scope and existing_cover_letter:
        chunks: list[str] = []
        try:
            for chunk in llm.refine_cover_letter(
                existing_cover_letter, strategy, feedback, eff_model, provider=eff_provider
            ):
                chunks.append(chunk)
        except llm.LLMError:
            pass
        if chunks:
            refined_cl = clean_llm_output("".join(chunks))
            if refined_cl.strip():
                cl_md = f"# Cover Letter — {job.title} @ {job.company}\n\n{refined_cl}\n"
                (folder / "cover_letter.md").write_text(cl_md, encoding="utf-8")
                changed_paths.append("cover_letter.md")
                try:
                    cl_html = render.markdown_to_html(cl_md, title=f"Cover Letter — {job.title}")
                    (folder / "cover_letter.html").write_text(cl_html, encoding="utf-8")
                    render.html_to_pdf(folder / "cover_letter.html", folder / "cover_letter.pdf")
                    changed_paths.append("cover_letter.html")
                    changed_paths.append("cover_letter.pdf")
                    if cfg.get("generate_docx", False):
                        render.markdown_to_docx(cl_md, folder / "cover_letter.docx")
                        changed_paths.append("cover_letter.docx")
                except Exception:
                    pass

    # --- Refine email ---
    if "email" in in_scope and existing_email:
        chunks: list[str] = []
        try:
            for chunk in llm.refine_email_inmail(
                existing_email, strategy, feedback, eff_model, provider=eff_provider
            ):
                chunks.append(chunk)
        except llm.LLMError:
            pass
        if chunks:
            refined_email = clean_llm_output("".join(chunks))
            if refined_email.strip():
                (folder / "email_inmail.md").write_text(
                    f"# Outreach — {job.title} @ {job.company}\n\n{refined_email}\n",
                    encoding="utf-8",
                )
                changed_paths.append("email_inmail.md")

    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "package_folder": str(folder),
        "artifacts": [{"name": p, "path": str(folder / p), "kind": Path(p).stem} for p in changed_paths],
        "version_folder": str(v_folder),
        "status": "complete",
    }
