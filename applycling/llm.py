"""Ollama integration layer."""

from __future__ import annotations

from typing import Iterator

import ollama

from .prompts import (
    FIT_SUMMARY_PROMPT,
    POSITIONING_BRIEF_PROMPT,
    PROFILE_SUMMARY_PROMPT,
    ROLE_INTEL_PROMPT,
    TAILOR_RESUME_PROMPT,
)


class LLMError(Exception):
    """Raised when the LLM call fails in a way the CLI should surface."""


def _wrap_errors(exc: Exception) -> LLMError:
    msg = str(exc).lower()
    if isinstance(exc, ConnectionError) or "connection" in msg or "refused" in msg:
        return LLMError(
            "Ollama doesn't seem to be running. Start it with: `ollama serve`"
        )
    return LLMError(f"Ollama error: {exc}")


def get_available_models() -> list[str]:
    try:
        resp = ollama.list()
    except ollama.ResponseError as e:
        raise _wrap_errors(e) from e
    except Exception as e:
        raise _wrap_errors(e) from e

    models = []
    # The Ollama SDK returns either a dict {"models": [...]} or an object with .models
    raw_models = resp.get("models", []) if isinstance(resp, dict) else getattr(resp, "models", [])
    for m in raw_models:
        if isinstance(m, dict):
            name = m.get("model") or m.get("name")
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            models.append(name)
    return models


def _stream_chat(model: str, prompt: str) -> Iterator[str]:
    try:
        stream = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            content = ""
            if isinstance(chunk, dict):
                content = chunk.get("message", {}).get("content", "")
            else:
                msg = getattr(chunk, "message", None)
                if msg is not None:
                    content = getattr(msg, "content", "") or ""
            if content:
                yield content
    except ollama.ResponseError as e:
        raise _wrap_errors(e) from e
    except Exception as e:
        raise _wrap_errors(e) from e


def tailor_resume(
    resume: str,
    job_description: str,
    model: str,
    stories: str | None = None,
    strategy: str | None = None,
    voice_tone: str | None = None,
    never_fabricate: list[str] | None = None,
) -> Iterator[str]:
    stories_section = ""
    if stories:
        stories_section = (
            "\n- You have been given CANDIDATE STORIES below. "
            "Draw from these only when they genuinely strengthen this application for this specific role. "
            "Omit anything that isn't relevant."
        )
    voice_tone_section = ""
    if voice_tone:
        voice_tone_section = f" Candidate's voice and tone: {voice_tone}"
    never_fabricate_section = ""
    if never_fabricate:
        items = "; ".join(never_fabricate)
        never_fabricate_section = f"\n- Specifically NEVER fabricate: {items}."
    prompt = TAILOR_RESUME_PROMPT.format(
        resume=resume,
        job_description=job_description,
        stories_section=stories_section,
        voice_tone_section=voice_tone_section,
        never_fabricate_section=never_fabricate_section,
    )
    if strategy:
        prompt += f"\n\n=== POSITIONING STRATEGY (follow this closely) ===\n{strategy}\n"
    if stories:
        prompt += f"\n\n=== CANDIDATE STORIES (draw from when relevant) ===\n{stories}\n"
    yield from _stream_chat(model, prompt)


def get_fit_summary(
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = FIT_SUMMARY_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)


def role_intel(
    job_description: str,
    model: str,
    company_page_text: str | None = None,
    resume: str | None = None,
) -> Iterator[str]:
    """Role Intel: extract signal, build positioning strategy, score ATS match."""
    company_note = ""
    if company_page_text:
        company_note = "\nUse the company page text below to inform this section."
    candidate_section = ""
    if resume:
        candidate_section = "\nYou have the candidate's base resume below. Use it to assess keyword coverage and gaps."
    prompt = ROLE_INTEL_PROMPT.format(
        job_description=job_description,
        company_note=company_note,
        candidate_section=candidate_section,
    )
    if company_page_text:
        prompt += f"\n\n=== COMPANY PAGE TEXT ===\n{company_page_text}\n"
    if resume:
        prompt += f"\n\n=== CANDIDATE BASE RESUME ===\n{resume}\n"
    yield from _stream_chat(model, prompt)


def positioning_brief(
    role_intel: str, tailored_resume: str, job_description: str, model: str
) -> Iterator[str]:
    """Generate the positioning brief from role intel + tailored resume."""
    prompt = POSITIONING_BRIEF_PROMPT.format(
        role_intel=role_intel,
        tailored_resume=tailored_resume,
        job_description=job_description,
    )
    yield from _stream_chat(model, prompt)


def get_profile_summary(
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = PROFILE_SUMMARY_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)
