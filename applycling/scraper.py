"""Fetch a job posting URL and extract title, company, and JD text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JobPosting:
    title: str
    company: str
    description: str
    company_url: str = ""   # best-effort derived from the job page


_EXTRACT_PROMPT = """You are parsing a job posting webpage. Below is the raw visible text scraped from the page.

Extract the following fields and return ONLY a JSON object with these exact keys:
- "title": the job title (string)
- "company": the hiring company name (string)
- "description": the full job description text, including responsibilities, requirements, and any other relevant sections (string)

If a field cannot be determined, use an empty string.
Return ONLY the JSON object — no markdown fences, no explanation.

=== PAGE TEXT ===
{page_text}
"""


def _fetch_page(url: str) -> tuple[str, str]:
    """Return (visible_text, page_html) using headless Chromium."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        try:
            page.goto(url, wait_until="networkidle", timeout=20_000)
        except PWTimeout:
            pass
        text = page.inner_text("body")
        html = page.content()
        browser.close()
    return text, html


def _clean(text: str, max_chars: int = 12_000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text[:max_chars]


def _derive_company_url(job_url: str, html: str) -> str:
    """Best-effort: extract a company page URL from the job page HTML."""
    # LinkedIn job pages embed a link to the company page.
    li_match = re.search(
        r'href="(https://www\.linkedin\.com/company/[^"?]+)', html
    )
    if li_match:
        return li_match.group(1).rstrip("/")

    # Greenhouse / Lever often link to the company site in the header.
    gh_match = re.search(
        r'href="(https?://(?!.*greenhouse\.io|.*lever\.co)[^"]+)"[^>]*>(?:About|Company|Home)',
        html,
        re.IGNORECASE,
    )
    if gh_match:
        return gh_match.group(1)

    return ""


def fetch_job_posting(url: str, model: str) -> JobPosting:
    """Fetch *url*, extract title/company/description, and derive company URL."""
    import ollama as _ollama

    raw, html = _fetch_page(url)
    cleaned = _clean(raw)

    prompt = _EXTRACT_PROMPT.format(page_text=cleaned)
    response = _ollama.generate(model=model, prompt=prompt, stream=False)
    text = response.get("response", "").strip()

    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned non-JSON when extracting job details:\n{text}"
        ) from e

    company_url = _derive_company_url(url, html)

    return JobPosting(
        title=data.get("title", "").strip(),
        company=data.get("company", "").strip(),
        description=data.get("description", "").strip(),
        company_url=company_url,
    )


def fetch_company_context(url: str, model: str) -> str:
    """Scrape a company page and return a Markdown summary of the company."""
    import ollama as _ollama
    from .prompts import COMPANY_CONTEXT_PROMPT

    raw, _ = _fetch_page(url)
    cleaned = _clean(raw, max_chars=8_000)

    prompt = COMPANY_CONTEXT_PROMPT.format(page_text=cleaned)
    response = _ollama.generate(model=model, prompt=prompt, stream=False)
    return response.get("response", "").strip()
