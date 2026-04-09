"""Markdown → HTML and HTML → PDF rendering for resume packages.

The HTML and PDF are produced from the same source so what you see in Chrome
is exactly what lands in the PDF. Playwright (headless Chromium) handles the
PDF step so the print engine matches the browser engine.
"""

from __future__ import annotations

from pathlib import Path

# A clean, recruiter-ready resume style. Uses only system fonts so the
# document renders identically in Chrome, Preview, and headless Chromium.
RESUME_STYLE = """
@page { size: Letter; margin: 0.6in; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.42;
  color: #1a1a1a;
  max-width: 7.4in;
  margin: 0 auto;
  padding: 0;
}
h1 {
  font-size: 22pt;
  margin: 0 0 0.05in 0;
  font-weight: 700;
  letter-spacing: -0.5px;
}
h2 {
  font-size: 11pt;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin: 0.22in 0 0.05in 0;
  padding-bottom: 0.03in;
  border-bottom: 1px solid #444;
  font-weight: 700;
}
h3 {
  font-size: 11pt;
  margin: 0.13in 0 0.02in 0;
  font-weight: 600;
}
p { margin: 0.04in 0; }
ul { margin: 0.05in 0 0.1in 0; padding-left: 0.22in; }
li { margin: 0.03in 0; }
a { color: #1a1a1a; text-decoration: none; }
strong { font-weight: 600; }
em { font-style: italic; color: #555; }
hr { border: none; border-top: 0.5px solid #888; margin: 0.1in 0; }
""".strip()


def markdown_to_html(markdown_text: str, title: str = "Resume") -> str:
    """Render Markdown to a complete standalone HTML document.

    Uses python-markdown with the `extra` extension for tables/footnotes/etc.
    The output is a self-contained HTML file you can open in any browser.
    """
    try:
        import markdown as md
    except ImportError as e:
        raise RuntimeError(
            "python-markdown is not installed. "
            "Run `pip install markdown` inside your venv."
        ) from e

    body_html = md.markdown(
        markdown_text,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{RESUME_STYLE}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Render an HTML file to PDF using headless Chromium via Playwright.

    The browser engine is identical to what the user sees in Chrome, so the
    PDF and the browser preview match exactly.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright is not installed. Run `pip install playwright` and "
            "then `playwright install chromium` inside your venv."
        ) from e

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    file_url = html_path.resolve().as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(file_url, wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="Letter",
                margin={
                    "top": "0.6in",
                    "right": "0.6in",
                    "bottom": "0.6in",
                    "left": "0.6in",
                },
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            browser.close()


def render_resume(markdown_text: str, out_dir: Path, title: str = "Resume") -> dict[str, Path]:
    """Write resume.md, resume.html, and resume.pdf into `out_dir`.

    Returns a dict with paths to the three files.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "resume.md"
    html_path = out_dir / "resume.html"
    pdf_path = out_dir / "resume.pdf"

    md_path.write_text(markdown_text, encoding="utf-8")
    html = markdown_to_html(markdown_text, title=title)
    html_path.write_text(html, encoding="utf-8")
    html_to_pdf(html_path, pdf_path)

    return {"markdown": md_path, "html": html_path, "pdf": pdf_path}
