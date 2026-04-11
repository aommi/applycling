"""Markdown → HTML and HTML → PDF rendering for resume packages.

The HTML and PDF are produced from the same source so what you see in Chrome
is exactly what lands in the PDF. Playwright (headless Chromium) handles the
PDF step so the print engine matches the browser engine.
"""

from __future__ import annotations

from pathlib import Path

# ATS-safe, recruiter-ready resume style.
# - Arial throughout: universally supported, ATS-readable.
# - All spacing via line-height and padding, never empty div spacers.
# - No position:fixed, no CSS multi-column, no CSS Grid with gap.
# - All text is real HTML text nodes (no SVG/image text).
RESUME_STYLE = """
@page { size: letter; margin: 0.7in 0.75in; }
* { box-sizing: border-box; }
body {
  font-family: Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: #1a1a1a;
  max-width: 7in;
  margin: 0 auto;
  padding: 0;
}
h1 {
  font-family: Arial, sans-serif;
  font-size: 22pt;
  margin: 0 0 0.05in 0;
  font-weight: 700;
  letter-spacing: -0.5px;
}
h2 {
  font-family: Arial, sans-serif;
  font-size: 11pt;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin: 0.22in 0 0.05in 0;
  padding-bottom: 0.03in;
  border-bottom: 1px solid #444;
  font-weight: 700;
}
h3 {
  font-family: Arial, sans-serif;
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


def markdown_to_docx(markdown_text: str, docx_path: Path) -> None:
    """Convert Markdown text to a .docx file.

    Uses python-docx. US Letter, margins matching the HTML/PDF output.
    """
    try:
        from docx import Document
        from docx.shared import Pt, Inches
    except ImportError as e:
        raise RuntimeError(
            "python-docx is not installed. Run `pip install python-docx`."
        ) from e

    doc = Document()

    # Set page size and margins (US Letter).
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    # Set default font.
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(10.5)

    for line in markdown_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            p = doc.add_heading(stripped[4:], level=3)
            for run in p.runs:
                run.font.name = "Arial"
        elif stripped.startswith("## "):
            p = doc.add_heading(stripped[3:], level=2)
            for run in p.runs:
                run.font.name = "Arial"
        elif stripped.startswith("# "):
            p = doc.add_heading(stripped[2:], level=1)
            for run in p.runs:
                run.font.name = "Arial"
        elif stripped.startswith("- ") or stripped.startswith("* "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        elif stripped.startswith("<!--"):
            continue  # Skip HTML comments (tailoring log).
        elif stripped == "-->":
            continue
        else:
            doc.add_paragraph(stripped)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))


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
