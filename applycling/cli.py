"""applycling CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import llm, notion_connect, package, pdf_import, prompts, storage
from .tracker import STATUSES, Job, TrackerError, get_store

console = Console()

STATUS_STYLES = {
    "tailored": "blue",
    "applied": "yellow",
    "interview": "green",
    "offer": "bold green",
    "rejected": "dim",
}


def _clean_llm_output(text: str) -> str:
    """Strip common LLM artifacts from output before rendering."""
    import re as _re

    # Strip markdown code fences anywhere in the output.
    text = _re.sub(r"```[a-z]*\s*\n?", "", text)

    # Remove preamble: everything before the first markdown heading or bullet.
    # Models often write "Here's the revised resume:\n" before the actual content.
    first_content = _re.search(r"^(#{1,3} |\- |\* |\d+\. )", text, flags=_re.MULTILINE)
    if first_content and first_content.start() > 0:
        preamble = text[:first_content.start()]
        # Only strip if the preamble looks like LLM chatter (no headings/bullets).
        if not _re.search(r"^#{1,3} ", preamble, flags=_re.MULTILINE):
            text = text[first_content.start():]

    # Remove leaked prompt markers (=== SOMETHING ===).
    text = _re.sub(r"^===.*?===.*$", "", text, flags=_re.MULTILINE)

    # Remove trailing sign-off / offer to help.
    text = _re.sub(
        r"\n(?:Let me know|Feel free|I hope|By consistently|If you'd like|I can).*$",
        "", text, flags=_re.DOTALL | _re.IGNORECASE,
    )

    # Collapse excessive blank lines left by removals.
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _profile_header_markdown(profile: dict) -> str:
    """Build the static top section of the resume from stored profile fields."""
    lines = []
    name = profile.get("name", "").strip()
    if name:
        lines.append(f"# {name}\n")
    contact = " · ".join(filter(None, [
        profile.get("email", "").strip(),
        profile.get("phone", "").strip(),
        profile.get("location", "").strip(),
    ]))
    if contact:
        lines.append(contact)
    links = " · ".join(filter(None, [
        profile.get("linkedin", "").strip(),
        profile.get("github", "").strip(),
    ]))
    if links:
        lines.append(links)
    return "\n".join(lines)


def _read_multiline(prompt_text: str) -> str:
    console.print(f"[bold]{prompt_text}[/bold]")
    console.print("[dim]Paste the text, then type [bold]---[/bold] on its own line and press Enter to finish.[/dim]")
    lines: list[str] = []
    while True:
        try:
            line = input("> " if not lines else "  ")
        except EOFError:
            break
        if line.strip() == "---":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _require_config() -> dict:
    try:
        return storage.load_config()
    except storage.StorageError:
        console.print(
            "[red]No config found.[/red] Run [bold]applycling setup[/bold] first."
        )
        sys.exit(1)


def _require_resume() -> str:
    try:
        return storage.load_resume()
    except storage.StorageError:
        console.print(
            "[red]No base resume found.[/red] Run [bold]applycling setup[/bold] first."
        )
        sys.exit(1)


@click.group()
def main() -> None:
    """applycling — your clingy job-search companion."""


# ---------- setup ----------

def _setup_resume_from_pdf(model: str) -> str:
    """Interactive PDF import. Returns the cleaned Markdown."""
    while True:
        path_str = Prompt.ask("PDF path")
        # Tolerate quoted paths and escaped spaces from drag-and-drop.
        cleaned_path = path_str.strip().strip("'\"").replace("\\ ", " ")
        pdf_path = Path(cleaned_path).expanduser()
        if not pdf_path.exists():
            console.print(f"[red]File not found:[/red] {pdf_path}")
            continue

        try:
            console.print()
            with console.status(
                "[cyan]Extracting text from PDF...[/cyan]", spinner="dots"
            ):
                raw = pdf_import.extract_text(pdf_path)
        except pdf_import.PDFImportError as e:
            console.print(f"[red]{e}[/red]")
            continue

        skip_llm = Prompt.ask(
            "Clean up text with Ollama? (skip if using a large model on limited RAM)",
            choices=["yes", "skip"],
            default="yes",
        )
        if skip_llm == "skip":
            cleaned = raw
        else:
            try:
                parts: list[str] = []
                with console.status(
                    "[cyan]Cleaning into Markdown via Ollama...[/cyan]",
                    spinner="dots",
                ):
                    for chunk in pdf_import.clean_to_markdown(raw, model):
                        parts.append(chunk)
            except llm.LLMError as e:
                console.print(f"[red]{e}[/red]")
                sys.exit(1)
            cleaned = "".join(parts).strip()

        console.print()
        console.print(
            Panel(Markdown(cleaned), title="Extracted resume", style="cyan")
        )

        choice = Prompt.ask(
            "Looks right?",
            choices=["yes", "redo", "paste"],
            default="yes",
        )
        if choice == "yes":
            return cleaned
        if choice == "paste":
            return _read_multiline("Paste your base resume below:")
        # redo: loop and ask for a different PDF


@main.command()
def setup() -> None:
    """First-time setup: save base resume and pick an Ollama model."""
    console.print(Panel.fit("[bold]applycling — Setup[/bold]", style="cyan"))

    # Pick a model first so the PDF importer can use it.
    try:
        models = llm.get_available_models()
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    if not models:
        console.print(
            "[red]No Ollama models installed.[/red] Try: "
            "[bold]ollama pull llama3.2[/bold]"
        )
        sys.exit(1)

    console.print("\n[bold]Available Ollama models:[/bold]")
    for i, name in enumerate(models, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name}")
    choice = Prompt.ask(
        "Pick a model",
        choices=[str(i) for i in range(1, len(models) + 1)],
        default="1",
    )
    chosen_model = models[int(choice) - 1]

    # Pick how to provide the base resume.
    console.print()
    source = Prompt.ask(
        "Base resume input",
        choices=["pdf", "paste"],
        default="pdf",
    )
    if source == "pdf":
        resume = _setup_resume_from_pdf(chosen_model)
    else:
        resume = _read_multiline("Paste your base resume below:")

    if not resume:
        console.print("[red]Empty resume — aborting.[/red]")
        sys.exit(1)

    storage.save_resume(resume)
    storage.save_config({"model": chosen_model})

    # Collect personal details (stored separately, never passed to the LLM).
    console.print("\n[bold]Personal details[/bold] [dim](used verbatim in every resume — never rewritten by AI)[/dim]")
    existing = storage.load_profile() or {}
    profile = {
        "name":     Prompt.ask("Full name",       default=existing.get("name", "")),
        "email":    Prompt.ask("Email",            default=existing.get("email", "")),
        "phone":    Prompt.ask("Phone",            default=existing.get("phone", "")),
        "location": Prompt.ask("Location",         default=existing.get("location", "")),
        "linkedin": Prompt.ask("LinkedIn URL",     default=existing.get("linkedin", "")),
        "github":   Prompt.ask("GitHub URL",       default=existing.get("github", "")),
    }

    # Voice, tone, and hard boundaries.
    console.print("\n[bold]Writing style[/bold] [dim](injected into every tailoring prompt)[/dim]")
    profile["voice_tone"] = Prompt.ask(
        "Voice & tone",
        default=existing.get("voice_tone", "Direct, active voice, outcome-first. Short sentences. No em-dashes, no clichés."),
    )
    console.print("\n[bold]Never fabricate[/bold] [dim](hard boundary: the LLM will never invent these)[/dim]")
    console.print("[dim]Comma-separated list, e.g.: specific tools not in resume, domain experience not evidenced[/dim]")
    nf_default = ", ".join(existing.get("never_fabricate", []))
    nf_input = Prompt.ask("Never fabricate", default=nf_default or "specific tools or platforms not listed in resume or stories, domain experience not evidenced")
    profile["never_fabricate"] = [s.strip() for s in nf_input.split(",") if s.strip()]

    storage.save_profile({k: v for k, v in profile.items() if v})

    # Ensure Playwright browsers are installed (needed for PDF rendering).
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch()  # quick check — will fail if browsers missing
    except Exception:
        console.print("\n[yellow]Installing Playwright browsers (one-time)…[/yellow]")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False,
        )
        if result.returncode != 0:
            console.print(
                "[red]Playwright browser install failed.[/red] "
                "Run manually: [bold]playwright install chromium[/bold]"
            )

    console.print(
        Panel.fit(
            f"[green]Setup complete![/green]\n"
            f"Model: [bold]{chosen_model}[/bold]\n\n"
            f"Next steps:\n"
            f"  • Optional: [bold]applycling notion connect[/bold] "
            f"to use Notion as your tracker.\n"
            f"  • Then: [bold]applycling add[/bold] to tailor your resume to a job.",
            style="green",
        )
    )


# ---------- add ----------

@main.command()
@click.option("--async", "async_mode", is_flag=True, help="Skip input gates. Generate full package without stopping.")
@click.option("--url", "url_arg", default="", help="Job posting URL — skips the URL prompt.")
def add(async_mode: bool, url_arg: str) -> None:
    """Add a job: tailor a resume + assemble an application package."""
    cfg = _require_config()
    review_mode = cfg.get("review_mode", "interactive")
    if async_mode:
        review_mode = "async"
    base_resume = _require_resume()
    model = cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = cfg.get("provider", "ollama")
    profile = storage.load_profile()
    stories = storage.load_stories()

    # Token tracking: list of (step_name, prompt_text, output_text).
    token_steps: list[tuple[str, str, str]] = []

    source_url = url_arg or (
        "" if async_mode else Prompt.ask("Job posting URL (leave blank to enter details manually)", default="")
    )
    title = company = job_description = ""

    company_url = ""
    if source_url:
        from . import scraper
        try:
            with console.status("[cyan]Fetching job posting...[/cyan]", spinner="dots"):
                posting, scrape_tokens = scraper.fetch_job_posting(source_url, model)
            if scrape_tokens[0]:  # Empty when structured data was used (no LLM call).
                token_steps.append(("Job scraping", scrape_tokens[0], scrape_tokens[1]))
            else:
                token_steps.append(("Job scraping (HTML)", "", ""))
                console.print("[dim]Extracted from structured data — no LLM call needed.[/dim]")
            title = posting.title
            company = posting.company
            job_description = posting.description
            company_url = posting.company_url
            console.print(f"[green]Fetched:[/green] [bold]{title}[/bold] @ [bold]{company}[/bold]")
            if not async_mode:
                title = Prompt.ask("Job title", default=title)
                company = Prompt.ask("Company name", default=company)
                if company_url:
                    console.print(f"[dim]Company page detected: {company_url}[/dim]")
                company_url = Prompt.ask("Company page URL (for context)", default=company_url)
            elif company_url:
                console.print(f"[dim]Company page detected: {company_url}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not auto-fetch details ({e}) — falling back to manual entry.[/yellow]")
            source_url = ""

    if not source_url:
        if async_mode:
            console.print("[red]--async requires --url. No URL provided and no fallback in async mode.[/red]")
            sys.exit(1)
        title = Prompt.ask("Job title")
        company = Prompt.ask("Company name")
        source_url = Prompt.ask("Source URL (optional)", default="")
        company_url = Prompt.ask("Company page URL (optional)", default="")
        job_description = _read_multiline("Paste the job description below (end with --- on its own line):")

    if not job_description:
        console.print("[red]Empty job description — aborting.[/red]")
        sys.exit(1)

    want_summary = True if async_mode else Prompt.ask(
        "Include a profile summary section?", choices=["y", "n"], default="y"
    ) == "y"

    if stories:
        console.print("[dim]Stories file found — will be considered during tailoring.[/dim]")

    # ---- Fetch company page text (optional, no LLM call) ----
    company_page_text = ""
    if company_url:
        try:
            from . import scraper as _scraper
            with console.status("[cyan]Fetching company page...[/cyan]", spinner="dots"):
                company_page_text = _scraper.fetch_page_text(company_url)
        except Exception as e:
            console.print(f"[yellow]Company page fetch failed ({e}) — skipping.[/yellow]")

    # ---- Role Intel (single merged pass) ----
    console.print()
    intel_parts: list[str] = []
    try:
        with console.status("[cyan]Running Role Intel...[/cyan]", spinner="dots"):
            for chunk in llm.role_intel(
                job_description, model,
                company_page_text=company_page_text or None,
                resume=base_resume,
                provider=provider,
            ):
                intel_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    strategy = _clean_llm_output("".join(intel_parts))
    _co_note = "\nUse the company page text below to inform this section." if company_page_text else ""
    _cand_section = "\nYou have the candidate's base resume below. Use it to assess keyword coverage and gaps."
    _intel_prompt = prompts.ROLE_INTEL_PROMPT.format(
        job_description=job_description, company_note=_co_note, candidate_section=_cand_section
    )
    if company_page_text:
        _intel_prompt += f"\n\n=== COMPANY PAGE TEXT ===\n{company_page_text}\n"
    _intel_prompt += f"\n\n=== CANDIDATE BASE RESUME ===\n{base_resume}\n"
    token_steps.append(("Role Intel", _intel_prompt, strategy))

    # Show Role Intel and structured input gate.
    console.print(Panel(strategy, title="[bold]Role Intel[/bold]", style="cyan"))
    if review_mode == "interactive":
        # Structured questions instead of generic y/n.
        import re as _re
        niche_match = _re.search(r"## Identified niche\s*\n(.+)", strategy)
        niche_text = niche_match.group(1).strip() if niche_match else "see above"
        console.print(f"\n[bold]Angle:[/bold] {niche_text}")
        angle_ok = Prompt.ask("Does this angle feel right, or do you want to lead with something else?", default="looks good")
        if angle_ok.lower() not in ("looks good", "yes", "y", "good", ""):
            strategy += f"\n\n## Candidate override\nLead with this angle instead: {angle_ok}\n"

        gaps_match = _re.search(r"## Tooling or domain gaps\s*\n([\s\S]*?)(?=\n##|$)", strategy)
        if gaps_match and gaps_match.group(1).strip() and "no gap" not in gaps_match.group(1).lower():
            console.print(f"\n[bold]Gaps identified:[/bold]\n{gaps_match.group(1).strip()}")
            gap_action = Prompt.ask("How to handle gaps? (bridge / deprioritise / other)", default="bridge")
            strategy += f"\n\n## Gap handling\nCandidate chose: {gap_action}\n"

        if Prompt.ask("Proceed to resume tailoring?", choices=["y", "edit"], default="y") == "edit":
            strategy = _read_multiline("Paste your edited strategy:")
    else:
        console.print("[dim]Async mode — auto-proceeding.[/dim]")

    # ---- Pass 2: Resume Tailor ----
    tailored_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Tailoring your resume...[/cyan]", spinner="dots"
        ):
            for chunk in llm.tailor_resume(
                base_resume, job_description, model,
                stories=stories, strategy=strategy,
                voice_tone=profile.get("voice_tone") if profile else None,
                never_fabricate=profile.get("never_fabricate") if profile else None,
                provider=provider,
            ):
                tailored_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    tailored_body = _clean_llm_output("".join(tailored_parts))
    _stories_section = (
        "\n- You have been given CANDIDATE STORIES below. "
        "Draw from these only when they genuinely strengthen this application for this specific role. "
        "Omit anything that isn't relevant."
    ) if stories else ""
    _vt = f" Candidate's voice and tone: {profile['voice_tone']}" if profile and profile.get("voice_tone") else ""
    _nf_list = profile.get("never_fabricate", []) if profile else []
    _nf = f"\n- Specifically NEVER fabricate: {'; '.join(_nf_list)}." if _nf_list else ""
    _tailor_prompt = prompts.TAILOR_RESUME_PROMPT.format(
        resume=base_resume, job_description=job_description,
        stories_section=_stories_section, voice_tone_section=_vt,
        never_fabricate_section=_nf,
    )
    if strategy:
        _tailor_prompt += f"\n\n=== POSITIONING STRATEGY (follow this closely) ===\n{strategy}\n"
    if stories:
        _tailor_prompt += f"\n\n=== CANDIDATE STORIES (draw from when relevant) ===\n{stories}\n"
    token_steps.append(("Resume Tailor", _tailor_prompt, tailored_body))

    # Optionally generate a per-job profile summary.
    profile_summary = ""
    if want_summary:
        summary_parts: list[str] = []
        try:
            with console.status(
                "[cyan]Generating profile summary...[/cyan]", spinner="dots"
            ):
                for chunk in llm.get_profile_summary(base_resume, job_description, model, provider=provider):
                    summary_parts.append(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Profile summary failed ({e}) — skipping.[/yellow]")
        profile_summary = _clean_llm_output("".join(summary_parts))
        if profile_summary:
            _ps_prompt = prompts.PROFILE_SUMMARY_PROMPT.format(
                resume=base_resume, job_description=job_description
            )
            token_steps.append(("Profile Summary", _ps_prompt, profile_summary))

    # Assemble the final resume: static profile header + optional summary + tailored body.
    resume_sections = []
    if profile:
        resume_sections.append(_profile_header_markdown(profile))
    if profile_summary:
        resume_sections.append(f"## Profile\n\n{profile_summary}")
    resume_sections.append(tailored_body)
    tailored = "\n\n".join(resume_sections)

    # Positioning brief (replaces fit summary — includes decisions, strength, gap prep).
    brief_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Generating positioning brief...[/cyan]", spinner="dots"
        ):
            for chunk in llm.positioning_brief(strategy, tailored, job_description, model, provider=provider):
                brief_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    pos_brief = _clean_llm_output("".join(brief_parts))
    _brief_prompt = prompts.POSITIONING_BRIEF_PROMPT.format(
        role_intel=strategy, tailored_resume=tailored, job_description=job_description
    )
    token_steps.append(("Positioning Brief", _brief_prompt, pos_brief))

    # ---- Cover letter ----
    cover_letter_text = ""
    cl_parts: list[str] = []
    try:
        with console.status("[cyan]Writing cover letter...[/cyan]", spinner="dots"):
            for chunk in llm.cover_letter(
                strategy, tailored, job_description, model,
                voice_tone=profile.get("voice_tone") if profile else None,
                provider=provider,
            ):
                cl_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[yellow]Cover letter generation failed ({e}) — skipping.[/yellow]")
    cover_letter_text = _clean_llm_output("".join(cl_parts))
    if cover_letter_text:
        _vt = f" Candidate's voice and tone: {profile['voice_tone']}" if profile and profile.get("voice_tone") else ""
        _cl_prompt = prompts.COVER_LETTER_PROMPT.format(
            role_intel=strategy, tailored_resume=tailored,
            job_description=job_description, voice_tone_section=_vt,
        )
        token_steps.append(("Cover Letter", _cl_prompt, cover_letter_text))

    # ---- Application email + LinkedIn InMail ----
    email_inmail_text = ""
    if profile:
        ei_parts: list[str] = []
        contact_line = " · ".join(filter(None, [
            profile.get("email", ""), profile.get("phone", ""),
        ]))
        try:
            with console.status("[cyan]Drafting email + InMail...[/cyan]", spinner="dots"):
                for chunk in llm.application_email(
                    strategy, profile.get("name", ""), contact_line,
                    title, company, model,
                    voice_tone=profile.get("voice_tone"),
                    provider=provider,
                ):
                    ei_parts.append(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Email/InMail generation failed ({e}) — skipping.[/yellow]")
        email_inmail_text = _clean_llm_output("".join(ei_parts))
        if email_inmail_text:
            _vt = f" Candidate's voice and tone: {profile['voice_tone']}" if profile.get("voice_tone") else ""
            _ei_prompt = prompts.APPLICATION_EMAIL_PROMPT.format(
                role_intel=strategy, candidate_name=profile.get("name", ""),
                candidate_contact=contact_line, job_title=title,
                company=company, voice_tone_section=_vt,
            )
            token_steps.append(("Email + InMail", _ei_prompt, email_inmail_text))

    # Also generate a short fit summary for the Notion row.
    fit_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Generating fit summary...[/cyan]", spinner="dots"
        ):
            for chunk in llm.get_fit_summary(base_resume, job_description, model, provider=provider):
                fit_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    fit_summary = _clean_llm_output("".join(fit_parts))
    _fit_prompt = prompts.FIT_SUMMARY_PROMPT.format(
        resume=base_resume, job_description=job_description
    )
    token_steps.append(("Fit Summary", _fit_prompt, fit_summary))

    # Persist the job (auto-assigns id + dates).
    store = get_store()
    job = Job(
        id="",
        title=title,
        company=company,
        date_added="",
        date_updated="",
        status="tailored",
        source_url=source_url or None,
        fit_summary=fit_summary or None,
    )
    try:
        job = store.save_job(job)
    except TrackerError as e:
        console.print(f"[red]Failed to save job:[/red] {e}")
        sys.exit(1)

    # Build the application package folder (md + html + pdf + manifest).
    try:
        with console.status(
            "[cyan]Rendering HTML + PDF and assembling package...[/cyan]",
            spinner="dots",
        ):
            folder = package.assemble(
                job, tailored, fit_summary,
                strategy=strategy or None,
                company_context=company_page_text or None,
                positioning_brief=pos_brief or None,
                cover_letter=cover_letter_text or None,
                email_inmail=email_inmail_text or None,
                generate_docx=cfg.get("generate_docx", False),
            )
    except Exception as e:
        console.print(f"[red]Package assembly failed:[/red] {e}")
        sys.exit(1)

    # Record the package folder back on the tracker row.
    try:
        job = store.update_job(job.id, package_folder=str(folder))
    except TrackerError as e:
        console.print(
            f"[yellow]Saved package but failed to record folder path:[/yellow] {e}"
        )

    console.print()
    console.print(
        Panel(
            fit_summary or "[dim](no summary)[/dim]",
            title="Fit Summary",
            style="magenta",
        )
    )
    console.print(f"\n[green]Package folder:[/green] [bold]{folder}[/bold]")
    console.print(f"[green]Tracked as:[/green] [bold]{job.id}[/bold]")

    # Token usage estimate — per-step breakdown.
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total_in = total_out = 0
        step_lines = []
        for step_name, prompt_text, output_text in token_steps:
            if not prompt_text and not output_text:
                step_lines.append(f"  {step_name:<20}      0 tokens (structured data)")
                continue
            s_in = len(enc.encode(prompt_text))
            s_out = len(enc.encode(output_text))
            total_in += s_in
            total_out += s_out
            step_lines.append(f"  {step_name:<20} {s_in:>6,} in + {s_out:>6,} out")
        total = total_in + total_out
        costs = [
            ("Gemini 2.0 Flash",  0.10,  0.40),
            ("GPT-4o mini",       0.15,  0.60),
            ("Claude Haiku 3.5",  0.80,  4.00),
            ("GPT-4o",            2.50, 10.00),
            ("Claude Sonnet 3.7", 3.00, 15.00),
            ("Gemini 2.5 Pro",    2.50, 15.00),
            ("o4-mini",           1.10,  4.40),
            ("Claude Opus 4",    15.00, 75.00),
            ("o3",               10.00, 40.00),
        ]
        cost_lines = "\n".join(
            f"  {name:<22} ${(total_in * inp + total_out * out) / 1_000_000:.4f}"
            for name, inp, out in costs
        )
        breakdown = "\n".join(step_lines)
        console.print(
            f"\n[dim]Token usage (tiktoken cl100k):\n"
            f"{breakdown}\n"
            f"  {'─' * 40}\n"
            f"  {'Total':<20} {total_in:>6,} in + {total_out:>6,} out = {total:,}\n\n"
            f"  API cost estimate:\n{cost_lines}[/dim]"
        )
    except Exception:
        pass


# ---------- list / view / status ----------

@main.command(name="list")
def list_jobs() -> None:
    """List all tracked jobs."""
    try:
        jobs = get_store().load_jobs()
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    if not jobs:
        console.print("[dim]No jobs tracked yet. Run `applycling add`.[/dim]")
        return

    table = Table(title="Tracked Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Company", style="bold")
    table.add_column("Title")
    table.add_column("Date")
    table.add_column("Status")
    for j in jobs:
        style = STATUS_STYLES.get(j.status, "white")
        table.add_row(
            j.id or "?",
            j.company or "?",
            j.title or "?",
            (j.date_added or "?").split("T")[0],
            f"[{style}]{j.status}[/{style}]",
        )
    console.print(table)


@main.command()
@click.argument("job_id")
def status(job_id: str) -> None:
    """Update the status of a tracked job."""
    store = get_store()
    try:
        job = store.load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(
        f"Current status for [bold]{job.id}[/bold] "
        f"({job.company or '?'} — {job.title or '?'}): "
        f"[{STATUS_STYLES.get(job.status, 'white')}]{job.status}[/]"
    )
    new_status = Prompt.ask(
        "New status", choices=list(STATUSES), default=job.status
    )
    try:
        store.update_job(job_id, status=new_status)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"[green]Updated[/green] {job_id} → [bold]{new_status}[/bold]")


@main.command()
@click.argument("job_id")
def view(job_id: str) -> None:
    """View the tailored resume for a job."""
    try:
        job = get_store().load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    folder = job.package_folder
    if not folder:
        console.print("[red]No package folder recorded for this job.[/red]")
        sys.exit(1)
    md_path = Path(folder) / "resume.md"
    if not md_path.exists():
        console.print(f"[red]Tailored resume file is missing:[/red] {md_path}")
        sys.exit(1)
    text = md_path.read_text(encoding="utf-8")
    console.print(
        Panel(
            f"[bold]{job.company or '?'}[/bold] — {job.title or '?'}  "
            f"[dim]({job.id})[/dim]",
            style="cyan",
        )
    )
    console.print(Markdown(text))


# ---------- notion subgroup ----------

@main.group()
def notion() -> None:
    """Notion integration commands."""


@notion.command(name="connect")
def notion_connect_cmd() -> None:
    """Interactive setup for Notion as the job tracker backend."""
    notion_connect.run()


if __name__ == "__main__":
    main()
