"""LLM integration layer — supports Ollama, Anthropic, and Google AI Studio."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from .skills import load_skill

# Load .env from repo root so API keys are available.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass


class LLMError(Exception):
    """Raised when the LLM call fails in a way the CLI should surface."""


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

def _stream_chat(model: str, prompt: str, provider: str = "ollama") -> Iterator[str]:
    """Route a prompt to the right provider and yield text chunks."""
    if provider == "anthropic":
        yield from _stream_anthropic(model, prompt)
    elif provider == "google":
        yield from _stream_google(model, prompt)
    elif provider == "openai":
        yield from _stream_openai(model, prompt)
    else:
        yield from _stream_ollama(model, prompt)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _stream_ollama(model: str, prompt: str) -> Iterator[str]:
    try:
        import ollama
    except ImportError as e:
        raise LLMError("ollama package is not installed.") from e
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
    except Exception as e:
        msg = str(e).lower()
        if "connection" in msg or "refused" in msg:
            raise LLMError(
                "Ollama doesn't seem to be running. Start it with: `ollama serve`"
            ) from e
        raise LLMError(f"Ollama error: {e}") from e


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _stream_anthropic(model: str, prompt: str) -> Iterator[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("anthropic package is not installed. Run: pip install anthropic") from e
    try:
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        raise LLMError(f"Anthropic error: {e}") from e


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _stream_openai(model: str, prompt: str) -> Iterator[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMError(
            "OPENAI_API_KEY is not set. Add it to your .env file."
        )
    try:
        import openai
    except ImportError as e:
        raise LLMError("openai package is not installed. Run: pip install openai") from e
    try:
        client = openai.OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text
    except Exception as e:
        raise LLMError(f"OpenAI error: {e}") from e


# ---------------------------------------------------------------------------
# Google AI Studio (Gemini)
# ---------------------------------------------------------------------------

def _stream_google(model: str, prompt: str) -> Iterator[str]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise LLMError(
            "GOOGLE_API_KEY is not set. Add it to your .env file."
        )
    try:
        from google import genai
    except ImportError as e:
        raise LLMError("google-genai package is not installed. Run: pip install google-genai") from e
    try:
        client = genai.Client(api_key=api_key)
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=prompt,
        ):
            if chunk.text:
                yield chunk.text
    except Exception as e:
        raise LLMError(f"Google AI error: {e}") from e


# ---------------------------------------------------------------------------
# Vision — extract text from images
# ---------------------------------------------------------------------------

_VISION_PROMPT = (
    "Extract all text from this image, preserving the original structure "
    "(paragraphs, lists, etc.). "
    "If you can confidently infer the source, add a one-line header with context "
    "(e.g. 'Source: Slack message from Jane Smith' or 'Source: LinkedIn InMail from recruiter'). "
    "Then the extracted text. No other commentary."
)


def extract_image_text(image_path: Path, model: str, provider: str = "ollama") -> str:
    """Extract text from an image file using a vision-capable model.

    Returns the extracted text. Raises LLMError if the model or provider
    doesn't support vision or the call fails.
    """
    import base64
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    suffix = image_path.suffix.lower().lstrip(".")
    mime_map = {"jpg": "jpeg", "tiff": "tiff"}
    mime = f"image/{mime_map.get(suffix, suffix)}"

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set.")
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("anthropic package is not installed.") from e
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
        )
        return resp.content[0].text

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set.")
        try:
            import openai
        except ImportError as e:
            raise LLMError("openai package is not installed.") from e
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
        )
        return resp.choices[0].message.content

    if provider == "google":
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise LLMError("GOOGLE_API_KEY is not set.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMError("google-genai package is not installed.") from e
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=data, mime_type=mime),
                _VISION_PROMPT,
            ],
        )
        return resp.text

    # Ollama
    try:
        import ollama
    except ImportError as e:
        raise LLMError("ollama package is not installed.") from e
    try:
        resp = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": _VISION_PROMPT,
                "images": [b64],
            }],
        )
        if isinstance(resp, dict):
            return resp.get("message", {}).get("content", "")
        return getattr(resp.message, "content", "") or ""
    except Exception as e:
        raise LLMError(f"Ollama vision error: {e}") from e


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------

def get_available_models() -> list[str]:
    """Return locally available Ollama models."""
    try:
        import ollama
    except ImportError:
        return []
    try:
        resp = ollama.list()
    except Exception:
        return []

    models = []
    raw_models = resp.get("models", []) if isinstance(resp, dict) else getattr(resp, "models", [])
    for m in raw_models:
        if isinstance(m, dict):
            name = m.get("model") or m.get("name")
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            models.append(name)
    return models


# ---------------------------------------------------------------------------
# Public API — all functions accept an optional `provider` kwarg
# ---------------------------------------------------------------------------

def tailor_resume(
    resume: str,
    job_description: str,
    model: str,
    stories: str | None = None,
    strategy: str | None = None,
    voice_tone: str | None = None,
    never_fabricate: list[str] | None = None,
    linkedin_profile: str | None = None,
    provider: str = "ollama",
) -> Iterator[str]:
    stories_section = ""
    if stories:
        stories_section = (
            "\n- You have been given CANDIDATE STORIES below. "
            "Draw from these only when they genuinely strengthen this application for this specific role. "
            "Omit anything that isn't relevant."
        )
    if linkedin_profile:
        stories_section += (
            "\n- You have been given the candidate's LINKEDIN PROFILE below. "
            "It may contain fuller descriptions, older roles, or additional context not in the resume. "
            "Draw from it only where it genuinely adds signal for this specific role."
        )
    voice_tone_section = ""
    if voice_tone:
        voice_tone_section = f" Candidate's voice and tone: {voice_tone}"
    never_fabricate_section = ""
    if never_fabricate:
        items = "; ".join(never_fabricate)
        never_fabricate_section = f"\n- Specifically NEVER fabricate: {items}."
    prompt = load_skill("resume_tailor").render(
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
    if linkedin_profile:
        prompt += f"\n\n=== LINKEDIN PROFILE (draw from when relevant) ===\n{linkedin_profile}\n"
    yield from _stream_chat(model, prompt, provider)


def get_fit_summary(
    resume: str, job_description: str, model: str, provider: str = "ollama"
) -> Iterator[str]:
    prompt = load_skill("fit_summary").render(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt, provider)


def role_intel(
    job_description: str,
    model: str,
    company_page_text: str | None = None,
    resume: str | None = None,
    provider: str = "ollama",
) -> Iterator[str]:
    company_note = ""
    if company_page_text:
        company_note = "\nUse the company page text below to inform this section."
    candidate_section = ""
    if resume:
        candidate_section = "\nYou have the candidate's base resume below. Use it to assess keyword coverage and gaps."
    prompt = load_skill("role_intel").render(
        job_description=job_description,
        company_note=company_note,
        candidate_section=candidate_section,
    )
    if company_page_text:
        prompt += f"\n\n=== COMPANY PAGE TEXT ===\n{company_page_text}\n"
    if resume:
        prompt += f"\n\n=== CANDIDATE BASE RESUME ===\n{resume}\n"
    yield from _stream_chat(model, prompt, provider)


def positioning_brief(
    role_intel: str, tailored_resume: str, job_description: str, model: str, provider: str = "ollama"
) -> Iterator[str]:
    prompt = load_skill("positioning_brief").render(
        role_intel=role_intel,
        tailored_resume=tailored_resume,
        job_description=job_description,
    )
    yield from _stream_chat(model, prompt, provider)


def cover_letter(
    role_intel_text: str,
    tailored_resume: str,
    job_description: str,
    model: str,
    voice_tone: str | None = None,
    provider: str = "ollama",
) -> Iterator[str]:
    vt = f" Candidate's voice and tone: {voice_tone}" if voice_tone else ""
    prompt = load_skill("cover_letter").render(
        role_intel=role_intel_text,
        tailored_resume=tailored_resume,
        job_description=job_description,
        voice_tone_section=vt,
    )
    yield from _stream_chat(model, prompt, provider)


def application_email(
    role_intel_text: str,
    candidate_name: str,
    candidate_contact: str,
    job_title: str,
    company: str,
    model: str,
    voice_tone: str | None = None,
    provider: str = "ollama",
) -> Iterator[str]:
    vt = f" Candidate's voice and tone: {voice_tone}" if voice_tone else ""
    prompt = load_skill("email_inmail").render(
        role_intel=role_intel_text,
        candidate_name=candidate_name,
        candidate_contact=candidate_contact,
        job_title=job_title,
        company=company,
        voice_tone_section=vt,
    )
    yield from _stream_chat(model, prompt, provider)


def get_profile_summary(
    resume: str, job_description: str, model: str, provider: str = "ollama"
) -> Iterator[str]:
    prompt = load_skill("profile_summary").render(
        resume=resume, job_description=job_description
    )
    yield from _stream_chat(model, prompt, provider)


def format_resume(
    resume: str, model: str, provider: str = "ollama"
) -> Iterator[str]:
    prompt = load_skill("format_resume").render(resume=resume)
    yield from _stream_chat(model, prompt, provider)


def refine_resume(
    resume: str,
    job_description: str,
    feedback: str,
    model: str,
    provider: str = "ollama",
) -> Iterator[str]:
    prompt = load_skill("refine_resume").render(
        feedback=feedback,
        resume=resume,
        job_description=job_description,
    )
    yield from _stream_chat(model, prompt, provider)


def refine_cover_letter(
    cover_letter: str,
    role_intel: str,
    feedback: str,
    model: str,
    provider: str = "ollama",
) -> Iterator[str]:
    prompt = load_skill("refine_cover_letter").render(
        feedback=feedback,
        cover_letter=cover_letter,
        role_intel=role_intel,
    )
    yield from _stream_chat(model, prompt, provider)


def refine_positioning_brief(
    brief: str,
    resume: str,
    role_intel: str,
    feedback: str,
    model: str,
    provider: str = "ollama",
) -> Iterator[str]:
    prompt = load_skill("refine_positioning_brief").render(
        feedback=feedback,
        resume=resume,
        brief=brief,
        role_intel=role_intel,
    )
    yield from _stream_chat(model, prompt, provider)


def interview_prep(
    job_description: str,
    resume: str,
    role_intel: str,
    model: str,
    positioning_brief: str = "",
    intel: str = "",
    stages: str = "recruiter screen, hiring manager deep-dive, technical, executive",
    provider: str = "ollama",
) -> Iterator[str]:
    intel_section = f"\n=== ADDITIONAL INTEL ===\n{intel}\n" if intel else ""
    prompt = load_skill("interview_prep").render(
        stages=stages,
        job_description=job_description,
        resume=resume,
        role_intel=role_intel,
        positioning_brief=positioning_brief or "(not provided)",
        intel_section=intel_section,
    )
    yield from _stream_chat(model, prompt, provider)


def critique(
    job_description: str,
    resume: str,
    role_intel: str,
    model: str,
    cover_letter: str = "",
    positioning_brief: str = "",
    provider: str = "ollama",
) -> Iterator[str]:
    prompt = load_skill("critique").render(
        job_description=job_description,
        resume=resume,
        cover_letter=cover_letter or "(not provided)",
        role_intel=role_intel,
        positioning_brief=positioning_brief or "(not provided)",
    )
    yield from _stream_chat(model, prompt, provider)


def generate_questions(
    job_description: str,
    resume: str,
    role_intel: str,
    model: str,
    positioning_brief: str = "",
    intel: str = "",
    existing_questions: str = "",
    stage: str = "all stages",
    count: int = 5,
    provider: str = "ollama",
) -> Iterator[str]:
    intel_section = f"\n=== ADDITIONAL INTEL ===\n{intel}\n" if intel else ""
    prompt = load_skill("questions").render(
        count=count,
        stage=stage,
        job_description=job_description,
        resume=resume,
        role_intel=role_intel,
        positioning_brief=positioning_brief or "(not provided)",
        intel_section=intel_section,
        existing_questions=existing_questions or "(none yet)",
    )
    yield from _stream_chat(model, prompt, provider)


def refine_email_inmail(
    email_inmail: str,
    role_intel: str,
    feedback: str,
    model: str,
    provider: str = "ollama",
) -> Iterator[str]:
    prompt = load_skill("refine_email_inmail").render(
        feedback=feedback,
        email_inmail=email_inmail,
        role_intel=role_intel,
    )
    yield from _stream_chat(model, prompt, provider)
