"""Ollama integration layer."""

from __future__ import annotations

from typing import Iterator

import ollama

from .prompts import FIT_SUMMARY_PROMPT, TAILOR_RESUME_PROMPT


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
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = TAILOR_RESUME_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)


def get_fit_summary(
    resume: str, job_description: str, model: str
) -> Iterator[str]:
    prompt = FIT_SUMMARY_PROMPT.format(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt)
