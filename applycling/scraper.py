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


def _extract_jsonld_job(html: str) -> dict | None:
    """Try to extract a JobPosting from JSON-LD structured data in the HTML.

    Returns a dict with title/company/description if found, else None.
    """
    # Find all JSON-LD script blocks.
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html,
        re.IGNORECASE,
    ):
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue

        # Handle both single objects and arrays (some sites use @graph).
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "@graph" in data:
                items = data["@graph"] if isinstance(data["@graph"], list) else [data["@graph"]]
            else:
                items = [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            schema_type = item.get("@type", "")
            if schema_type == "JobPosting" or (
                isinstance(schema_type, list) and "JobPosting" in schema_type
            ):
                title = item.get("title", "")
                description = item.get("description", "")
                # Strip HTML tags from description if present.
                description = re.sub(r"<[^>]+>", "", description)
                description = re.sub(r"&[a-z]+;", " ", description)
                description = re.sub(r"\s{2,}", " ", description).strip()

                company = ""
                org = item.get("hiringOrganization", {})
                if isinstance(org, dict):
                    company = org.get("name", "")

                if title or description:
                    return {
                        "title": title,
                        "company": company,
                        "description": description,
                    }
    return None


def _extract_from_meta_and_html(html: str) -> dict | None:
    """Try to extract job details from OG meta tags and HTML structure.

    Works for LinkedIn and other sites that embed job data in standard HTML
    rather than JSON-LD.
    """
    # Extract OG title — LinkedIn format: "{Company} hiring {Title} in {Location} | LinkedIn"
    og_title = ""
    og_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html)
    if og_match:
        og_title = og_match.group(1)

    title = company = ""
    # Parse LinkedIn's "{Company} hiring {Title} in {Location} | LinkedIn" format.
    hiring_match = re.match(r"^(.+?)\s+hiring\s+(.+?)\s+in\s+.+", og_title)
    if hiring_match:
        company = hiring_match.group(1).strip()
        title = hiring_match.group(2).strip()

    # Extract description from known HTML patterns.
    description = ""
    # LinkedIn's job description div.
    desc_match = re.search(
        r'<div[^>]*class="[^"]*show-more-less-html__markup[^"]*"[^>]*>([\s\S]*?)</div>',
        html,
    )
    if desc_match:
        description = desc_match.group(1)
        description = re.sub(r"<[^>]+>", "\n", description)
        description = re.sub(r"&[a-z]+;", " ", description)
        description = re.sub(r"\n{3,}", "\n\n", description)
        description = description.strip()

    if title and description:
        return {"title": title, "company": company, "description": description}
    return None


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


def fetch_job_posting(url: str, model: str) -> tuple[JobPosting, tuple[str, str]]:
    """Fetch *url*, extract title/company/description, and derive company URL.

    Tries JSON-LD structured data first (zero LLM tokens). Falls back to
    LLM extraction if no structured data is found.

    Returns (JobPosting, (prompt_text, output_text)) so callers can track
    token usage. When JSON-LD is used, prompt and output are both empty
    strings (no LLM call).
    """
    raw, html = _fetch_page(url)
    company_url = _derive_company_url(url, html)

    # Fast path: extract from structured data (no LLM needed).
    structured = _extract_jsonld_job(html) or _extract_from_meta_and_html(html)
    if structured and structured.get("description"):
        posting = JobPosting(
            title=structured.get("title", "").strip(),
            company=structured.get("company", "").strip(),
            description=structured.get("description", "").strip(),
            company_url=company_url,
        )
        return posting, ("", "")  # No LLM call — zero tokens.

    # Slow path: send page text to LLM for extraction.
    import ollama as _ollama

    cleaned = _clean(raw)
    prompt = _EXTRACT_PROMPT.format(page_text=cleaned)
    response = _ollama.generate(model=model, prompt=prompt, stream=False)
    text = response.get("response", "").strip()

    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    # Try to extract the JSON object even if the LLM added surrounding text.
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        text = json_match.group(0)

    # Small models often emit literal newlines inside JSON string values
    # instead of proper \n escapes.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fixed = re.sub(r'(?<=": ")([\s\S]*?)(?="[,\s*}])',
                        lambda m: m.group(0).replace("\n", "\\n"), text)
        try:
            data = json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM returned non-JSON when extracting job details:\n{text[:500]}"
            ) from e

    posting = JobPosting(
        title=data.get("title", "").strip(),
        company=data.get("company", "").strip(),
        description=data.get("description", "").strip(),
        company_url=company_url,
    )
    return posting, (prompt, text)


def fetch_page_text(url: str) -> str:
    """Fetch a page and return its cleaned visible text. No LLM call."""
    raw, _ = _fetch_page(url)
    return _clean(raw, max_chars=8_000)
