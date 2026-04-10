"""Ollama integration layer."""

from __future__ import annotations

from typing import Iterator

import ollama

from .prompts import (
    COMPANY_CONTEXT_PROMPT,
    FIT_SUMMARY_PROMPT,
    PROFILE_SUMMARY_PROMPT,
    ROLE_ANALYST_PROMPT,
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
    context: str | None = None,
    strategy: str | None = None,
) -> Iterator[str]:
    context_section = ""
    if context:
        context_section = (
            "\n- You have been given OPTIONAL CONTEXT below. "
            "Include items from it only if they genuinely strengthen this application for this specific role. "
            "Omit anything that isn't relevant."
        )
    prompt = TAILOR_RESUME_PROMPT.format(
        resume=resume,
        job_description=job_description,
        context_section=context_section,
    )
    if strategy:
        prompt += f"\n\n=== POSITIONING STRATEGY (follow this closely) ===\n{strategy}\n"
    if context:
        prompt += f"\n\n=== OPTIONAL CONTEXT (include only if relevant) ===\n{context}\n"
    yield from _stream_chat(model, prompt)


def get_fit_summary(
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = FIT_SUMMARY_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)


def analyze_role(
    job_description: str, model: str, company_context: str | None = None
) -> Iterator[str]:
    """Pass 1: extract role signal and produce a positioning strategy."""
    company_section = ""
    if company_context:
        company_section = f"\n\n=== COMPANY CONTEXT ===\n{company_context}"
    prompt = ROLE_ANALYST_PROMPT.format(
        job_description=job_description,
        company_section=company_section,
    )
    yield from _stream_chat(model, prompt)


def get_profile_summary(
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = PROFILE_SUMMARY_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)
