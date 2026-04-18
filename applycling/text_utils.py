"""Shared text helpers used by both cli and pipeline modules."""

from __future__ import annotations

import re as _re


def clean_llm_output(text: str) -> str:
    """Strip common LLM artifacts from output before rendering."""
    text = _re.sub(r"```[a-z]*\s*\n?", "", text)

    first_content = _re.search(r"^(#{1,3} |\- |\* |\d+\. )", text, flags=_re.MULTILINE)
    if first_content and first_content.start() > 0:
        preamble = text[: first_content.start()]
        if not _re.search(r"^#{1,3} ", preamble, flags=_re.MULTILINE):
            text = text[first_content.start() :]

    text = _re.sub(r"^===.*?===.*$", "", text, flags=_re.MULTILINE)

    text = _re.sub(
        r"\n(?:Let me know|Feel free|I hope|By consistently|If you'd like|I can).*$",
        "",
        text,
        flags=_re.DOTALL | _re.IGNORECASE,
    )

    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
