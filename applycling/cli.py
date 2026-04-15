"""applycling CLI."""

from __future__ import annotations

import datetime as _dt
import os
import sys
import uuid as _uuid
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import llm, notion_connect, package, pdf_import, prompts, render, storage
from .tracker import STATUSES, Job, TrackerError, get_store

console = Console()

STATUS_STYLES = {
    "tailored": "blue",
    "applied": "yellow",
    "interview": "green",
    "offer": "bold green",
    "rejected": "dim",
}


def _pick(question: str, options: list[str], default: str = "") -> str:
    """Interactive selector with arrow key navigation."""
    try:
        from InquirerPy import inquirer
        result = inquirer.select(
            message=question,
            choices=options,
            default=default if default in options else options[0],
        ).execute()
        return result if result is not None else (default or options[0])
    except ImportError:
        # Fallback to numbered list if InquirerPy isn't installed.
        console.print(f"\n{question}")
        for i, opt in enumerate(options, 1):
            marker = "[bold cyan]>[/bold cyan]" if opt == default else " "
            console.print(f"  {marker} [cyan]{i}[/cyan]. {opt}")
        default_idx = str(options.index(default) + 1) if default in options else "1"
        choice = Prompt.ask("Enter number", default=default_idx)
        try:
            return options[int(choice) - 1]
        except (ValueError, IndexError):
            return default or options[0]


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


class _Step:
    """Context manager that times a pipeline step and auto-appends to step_logs.

    Usage::

        step = _Step("role_intel", step_logs, output_file="strategy.md")
        step.prompt_text = prompt  # set before entering
        try:
            with step, console.status("..."):
                for chunk in llm.something(...):
                    step.collect(chunk)
        except llm.LLMError as e:
            ...
        result = _clean_llm_output(step.output)

    Any new pipeline step that uses this automatically gets timed, logged,
    and counted in the token breakdown — no manual wiring needed.
    """

    def __init__(self, name: str, logs: list[dict], output_file: str | None = None) -> None:
        self.name = name
        self._logs = logs
        self.output_file = output_file
        self.prompt_text: str = ""
        self.output: str = ""
        self.status: str = "ok"
        self.duration: float = 0.0
        self._parts: list[str] = []
        self._started: _dt.datetime | None = None

    def __enter__(self) -> "_Step":
        self._started = _dt.datetime.utcnow()
        return self

    def collect(self, chunk: str) -> None:
        self._parts.append(chunk)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        finished = _dt.datetime.utcnow()
        self.output = "".join(self._parts)
        self.duration = round((finished - self._started).total_seconds(), 2)
        if exc_type is not None:
            self.status = "failed"
        elif not self.output.strip():
            self.status = "skipped"
        self._logs.append({
            "name": self.name,
            "started_at": self._started.isoformat() + "Z",
            "finished_at": finished.isoformat() + "Z",
            "duration_seconds": self.duration,
            "output_file": self.output_file,
            "status": self.status,
            "prompt_text": self.prompt_text,
            "output_text": self.output,
        })
        return False  # Never suppress exceptions — caller handles them.


@click.group()
def main() -> None:
    """applycling — your clingy job-search companion."""


# ---------- setup ----------

def _setup_resume_from_pdf(model: str, provider: str = "ollama") -> str:
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

        cleaned = raw

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
    """First-time setup: save base resume and pick a model."""
    console.print(Panel.fit("[bold]applycling — Setup[/bold]", style="cyan"))

    existing_cfg = {}
    try:
        existing_cfg = storage.load_config()
    except storage.StorageError:
        pass

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    _BACK = "← back"

    # ---------------------------------------------------------------------------
    # Step helpers — each returns its result or _BACK sentinel
    # ---------------------------------------------------------------------------

    def _step_provider_model(prev_provider="", prev_model=""):
        console.print("\n[bold]Step 1 — LLM provider & model[/bold]")
        p = _pick("Provider", ["ollama", "anthropic", "openai", "google"],
                  default=prev_provider or existing_cfg.get("provider", "ollama"))
        if p == "ollama":
            try:
                models = llm.get_available_models()
            except llm.LLMError as e:
                console.print(f"[red]{e}[/red]"); sys.exit(1)
            if not models:
                console.print("[red]No Ollama models installed.[/red] Try: [bold]ollama pull llama3.2[/bold]")
                sys.exit(1)
        elif p == "anthropic":
            try:
                import anthropic as _a
                key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not key: raise ValueError()
                models = [m.id for m in _a.Anthropic(api_key=key).models.list().data]
            except Exception:
                models = ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6"]
                console.print("[dim]Could not fetch models — showing defaults.[/dim]")
        elif p == "openai":
            try:
                import openai as _o
                key = os.environ.get("OPENAI_API_KEY", "")
                if not key: raise ValueError()
                all_m = [m.id for m in _o.OpenAI(api_key=key).models.list().data]
                models = sorted([m for m in all_m if m.startswith(("gpt-", "o1", "o3", "o4"))])
            except Exception:
                models = ["gpt-4o", "gpt-4o-mini", "o3-mini"]
                console.print("[dim]Could not fetch models — showing defaults.[/dim]")
        else:  # google
            m = Prompt.ask("Model name", default=prev_model or existing_cfg.get("model", "gemini-2.0-flash"))
            return p, m
        default_m = prev_model if prev_model in models else (existing_cfg.get("model") if existing_cfg.get("model") in models else models[0])
        sel = _pick("Pick a model", models + [_BACK], default=default_m)
        if sel == _BACK:
            return _step_provider_model(prev_provider=p, prev_model="")
        return p, sel

    def _step_resume(prev_provider, prev_model):
        console.print("\n[bold]Step 2 — Base resume[/bold]")
        existing_resume = None
        try:
            existing_resume = storage.load_resume()
        except storage.StorageError:
            pass
        if existing_resume:
            choice = _pick("A base resume already exists.", ["keep", "replace", _BACK], default="keep")
            if choice == _BACK: return _BACK
            if choice == "keep": return existing_resume
        src = _pick("Base resume input", ["pdf", "paste", _BACK], default="pdf")
        if src == _BACK: return _BACK
        if src == "pdf":
            r = _setup_resume_from_pdf(prev_model, provider=prev_provider)
        else:
            r = _read_multiline("Paste your base resume below:")
        return r or _BACK

    def _step_profile():
        console.print("\n[bold]Step 3 — Personal details[/bold] [dim](never rewritten by AI)[/dim]")
        existing = storage.load_profile() or {}
        p = {
            "name":     Prompt.ask("Full name",   default=existing.get("name", "")),
            "email":    Prompt.ask("Email",        default=existing.get("email", "")),
            "phone":    Prompt.ask("Phone",        default=existing.get("phone", "")),
            "location": Prompt.ask("Location",     default=existing.get("location", "")),
            "linkedin": Prompt.ask("LinkedIn URL", default=existing.get("linkedin", "")),
            "github":   Prompt.ask("GitHub URL",   default=existing.get("github", "")),
        }
        console.print("\n[bold]Writing style[/bold] [dim](injected into every tailoring prompt)[/dim]")
        p["voice_tone"] = Prompt.ask(
            "Voice & tone",
            default=existing.get("voice_tone", "Direct, active voice, outcome-first. Short sentences. No em-dashes, no clichés."),
        )
        console.print("\n[bold]Never fabricate[/bold] [dim](comma-separated — the LLM will never invent these)[/dim]")
        nf_default = ", ".join(existing.get("never_fabricate", []))
        nf_input = Prompt.ask("Never fabricate", default=nf_default or "specific tools or platforms not listed in resume or stories, domain experience not evidenced")
        p["never_fabricate"] = [s.strip() for s in nf_input.split(",") if s.strip()]
        back = _pick("Continue?", ["continue", _BACK], default="continue")
        if back == _BACK: return _BACK
        return p

    def _step_output_settings():
        console.print("\n[bold]Step 4 — Output settings[/bold]")
        cfg_now = storage.load_config() if storage.CONFIG_PATH.exists() else {}
        run_log = _pick("Generate run_log.json per package?", ["yes", "no", _BACK],
                        default="yes" if cfg_now.get("generate_run_log", True) else "no")
        if run_log == _BACK: return _BACK
        docx = _pick("Generate .docx in addition to PDF?", ["yes", "no", _BACK],
                     default="yes" if cfg_now.get("generate_docx", False) else "no")
        if docx == _BACK: return _BACK
        existing_output_dir = cfg_now.get("output_dir", "")
        console.print(
            "\n[dim]Where should application packages be saved?[/dim]\n"
            "[dim]Leave blank for the default (./output inside this project).[/dim]\n"
            "[dim]Paste a Google Drive, iCloud, or Dropbox path to sync automatically.[/dim]"
        )
        if existing_output_dir:
            console.print(f"[dim]Current: {existing_output_dir}[/dim]")
        output_dir = Prompt.ask("Output directory", default=existing_output_dir or "").strip()
        if not output_dir:
            default_path = existing_output_dir or str(package.OUTPUT_DIR)
            console.print(f"[dim]Packages will be saved to: {default_path}[/dim]")
        result = {"generate_run_log": run_log == "yes", "generate_docx": docx == "yes"}
        if output_dir:
            result["output_dir"] = output_dir
        return result

    def _step_stories():
        console.print("\n[bold]Step 5 — Stories[/bold] [dim](optional extra experiences for tailoring)[/dim]")
        console.print("[dim]Side projects, consulting, part-time work, achievements not on your resume.[/dim]")
        existing_stories = storage.load_stories()
        if existing_stories:
            console.print(f"\n[dim]Current stories file ({len(existing_stories)} chars):[/dim]")
            console.print(Panel(existing_stories[:400] + ("…" if len(existing_stories) > 400 else ""), style="dim"))
            choice = _pick("Edit stories?", ["skip", "yes", _BACK], default="skip")
            if choice == _BACK: return _BACK
            if choice == "yes":
                console.print("[dim]Type [bold]---[/bold] immediately (no content) to skip and keep existing stories.[/dim]")
                new_stories = _read_multiline("Paste your updated stories below:")
                if new_stories:
                    storage.save_stories(new_stories)
                    console.print("[green]Stories updated.[/green]")
        else:
            choice = _pick("Add stories now?", ["skip", "yes", _BACK], default="skip")
            if choice == _BACK: return _BACK
            if choice == "yes":
                console.print("[dim]Type [bold]---[/bold] immediately (no content) to skip — you can add them later via [bold]applycling setup[/bold] or [bold]data/stories.md[/bold].[/dim]")
                new_stories = _read_multiline("Paste your stories below:")
                if new_stories:
                    storage.save_stories(new_stories)
                    console.print("[green]Stories saved.[/green]")
                else:
                    console.print("[dim]No stories saved. Add them later via [bold]applycling setup[/bold] or edit [bold]data/stories.md[/bold] directly.[/dim]")
            else:
                console.print("[dim]You can add them later — run [bold]applycling setup[/bold] again, or edit [bold]data/stories.md[/bold] directly.[/dim]")
        return {}

    def _step_linkedin():
        console.print("\n[bold]Step 6 — LinkedIn profile[/bold] [dim](optional, zero tokens)[/dim]")
        console.print("[dim]Export as PDF from LinkedIn (Me → Save to PDF) and provide the path.[/dim]")
        existing_linkedin = storage.load_linkedin_profile()
        if existing_linkedin:
            console.print(f"\n[dim]LinkedIn profile already imported ({len(existing_linkedin)} chars).[/dim]")
            choice = _pick("Re-import?", ["skip", "yes", _BACK], default="skip")
            if choice == _BACK: return _BACK
            if choice == "skip": return {}
        else:
            choice = _pick("Import LinkedIn PDF now?", ["yes", "skip", _BACK], default="skip")
            if choice == _BACK: return _BACK
            if choice == "skip":
                console.print("[dim]You can import it later: run [bold]applycling setup[/bold] again.[/dim]")
                return {}
        console.print("[dim]Leave blank to skip and import later via [bold]applycling setup[/bold].[/dim]")
        while True:
            li_path_str = Prompt.ask("LinkedIn PDF path", default="").strip()
            if not li_path_str:
                console.print("[dim]Skipped. You can import later via [bold]applycling setup[/bold].[/dim]")
                return {}
            li_path = Path(li_path_str.strip("'\"").replace("\\ ", " ")).expanduser()
            if not li_path.exists():
                console.print(f"[red]File not found:[/red] {li_path}")
                continue
            try:
                with console.status("[cyan]Extracting LinkedIn profile...[/cyan]", spinner="dots"):
                    li_text = pdf_import.extract_text(li_path)
                storage.save_linkedin_profile(li_text)
                console.print(f"[green]LinkedIn profile imported ({len(li_text)} chars).[/green]")
            except pdf_import.PDFImportError as e:
                console.print(f"[red]{e}[/red]")
            return {}

    # ---------------------------------------------------------------------------
    # Run steps in sequence; ← back at any step returns to the previous one
    # ---------------------------------------------------------------------------
    step = 0
    provider = existing_cfg.get("provider", "ollama")
    chosen_model = existing_cfg.get("model", "")
    resume = None
    profile_data = None
    output_settings = None

    while step <= 5:
        if step == 0:
            result = _step_provider_model(prev_provider=provider, prev_model=chosen_model)
            if result == _BACK:
                step = max(0, step - 1)
            else:
                provider, chosen_model = result
                storage.save_config({"provider": provider, "model": chosen_model})
                step += 1
        elif step == 1:
            result = _step_resume(provider, chosen_model)
            if result == _BACK:
                step -= 1
            else:
                resume = result
                storage.save_resume(resume)
                step += 1
        elif step == 2:
            result = _step_profile()
            if result == _BACK:
                step -= 1
            else:
                profile_data = result
                storage.save_profile({k: v for k, v in profile_data.items() if v})
                step += 1
        elif step == 3:
            result = _step_output_settings()
            if result == _BACK:
                step -= 1
            else:
                output_settings = result
                storage.save_config({**output_settings, "use_linkedin_profile": True})
                step += 1
        elif step == 4:
            result = _step_stories()
            if result == _BACK:
                step -= 1
            else:
                step += 1
        elif step == 5:
            result = _step_linkedin()
            if result == _BACK:
                step -= 1
            else:
                step += 1

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
@click.option("--model", "model_arg", default="", help="Override the model from config (e.g. gemma4:27b, claude-haiku-4-5-20251001).")
@click.option("--provider", "provider_arg", default="", help="Override the provider from config (ollama, anthropic, google).")
def add(async_mode: bool, url_arg: str, model_arg: str, provider_arg: str) -> None:
    """Add a job: tailor a resume + assemble an application package."""
    cfg = _require_config()
    review_mode = cfg.get("review_mode", "interactive")
    if async_mode:
        review_mode = "async"
    base_resume = _require_resume()
    model = model_arg or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = provider_arg or cfg.get("provider", "ollama")
    profile = storage.load_profile()
    stories = storage.load_stories()
    linkedin_profile = storage.load_linkedin_profile() if cfg.get("use_linkedin_profile", True) else None
    if linkedin_profile:
        console.print("[dim]LinkedIn profile found — will be considered during tailoring.[/dim]")

    # Run tracking.
    run_id = str(_uuid.uuid4())
    run_started = _dt.datetime.utcnow()
    step_logs: list[dict] = []

    source_url = url_arg or (
        "" if async_mode else Prompt.ask("Job posting URL (leave blank to enter details manually)", default="")
    )
    title = company = job_description = ""

    company_url = ""
    if source_url:
        from . import scraper
        try:
            _step_start = _dt.datetime.utcnow()
            with console.status("[cyan]Fetching job posting...[/cyan]", spinner="dots"):
                posting, scrape_tokens = scraper.fetch_job_posting(source_url, model, provider=provider)
            _step_end = _dt.datetime.utcnow()
            if scrape_tokens[0]:  # Empty when structured data was used (no LLM call).
                step_logs.append({"name": "job_scraping", "started_at": _step_start.isoformat() + "Z", "finished_at": _step_end.isoformat() + "Z", "duration_seconds": round((_step_end - _step_start).total_seconds(), 2), "status": "ok", "prompt_text": scrape_tokens[0], "output_text": scrape_tokens[1]})
            else:
                step_logs.append({"name": "job_scraping", "started_at": _step_start.isoformat() + "Z", "finished_at": _step_end.isoformat() + "Z", "duration_seconds": round((_step_end - _step_start).total_seconds(), 2), "status": "ok", "note": "structured data — no LLM call", "prompt_text": "", "output_text": ""})
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
    _co_note = "\nUse the company page text below to inform this section." if company_page_text else ""
    _cand_section = "\nYou have the candidate's base resume below. Use it to assess keyword coverage and gaps."
    _intel_prompt = prompts.ROLE_INTEL_PROMPT.format(
        job_description=job_description, company_note=_co_note, candidate_section=_cand_section
    )
    if company_page_text:
        _intel_prompt += f"\n\n=== COMPANY PAGE TEXT ===\n{company_page_text}\n"
    _intel_prompt += f"\n\n=== CANDIDATE BASE RESUME ===\n{base_resume}\n"
    _s = _Step("role_intel", step_logs, output_file="strategy.md")
    _s.prompt_text = _intel_prompt
    try:
        with _s, console.status("[cyan]Running Role Intel...[/cyan]", spinner="dots"):
            for chunk in llm.role_intel(
                job_description, model,
                company_page_text=company_page_text or None,
                resume=base_resume,
                provider=provider,
            ):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    strategy = _clean_llm_output(_s.output)

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
    if linkedin_profile:
        _tailor_prompt += f"\n\n=== LINKEDIN PROFILE (draw from when relevant) ===\n{linkedin_profile}\n"
    _s = _Step("resume_tailor", step_logs, output_file="resume.md")
    _s.prompt_text = _tailor_prompt
    try:
        with _s, console.status("[cyan]Tailoring your resume...[/cyan]", spinner="dots"):
            for chunk in llm.tailor_resume(
                base_resume, job_description, model,
                stories=stories, strategy=strategy,
                voice_tone=profile.get("voice_tone") if profile else None,
                never_fabricate=profile.get("never_fabricate") if profile else None,
                linkedin_profile=linkedin_profile,
                provider=provider,
            ):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    tailored_body = _clean_llm_output(_s.output)

    # Optionally generate a per-job profile summary.
    profile_summary = ""
    if want_summary:
        _s = _Step("profile_summary", step_logs)
        _s.prompt_text = prompts.PROFILE_SUMMARY_PROMPT.format(
            resume=base_resume, job_description=job_description
        )
        try:
            with _s, console.status("[cyan]Generating profile summary...[/cyan]", spinner="dots"):
                for chunk in llm.get_profile_summary(base_resume, job_description, model, provider=provider):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Profile summary failed ({e}) — skipping.[/yellow]")
        profile_summary = _clean_llm_output(_s.output)

    # ---- Format pass — reshape to preferred template (no content changes) ----
    _s = _Step("format_resume", step_logs, output_file="resume.md")
    _s.prompt_text = prompts.FORMAT_RESUME_PROMPT.format(resume=tailored_body)
    try:
        with _s, console.status("[cyan]Formatting resume...[/cyan]", spinner="dots"):
            for chunk in llm.format_resume(tailored_body, model, provider=provider):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[yellow]Format pass failed ({e}) — using unformatted output.[/yellow]")
    formatted_body = _clean_llm_output(_s.output) or tailored_body

    # Assemble the final resume: static profile header + optional summary + formatted body.
    resume_sections = []
    if profile:
        resume_sections.append(_profile_header_markdown(profile))
    if profile_summary:
        resume_sections.append(f"## PROFILE\n\n{profile_summary}")
    resume_sections.append(formatted_body)
    tailored = "\n\n".join(resume_sections)

    # Positioning brief (replaces fit summary — includes decisions, strength, gap prep).
    _s = _Step("positioning_brief", step_logs, output_file="positioning_brief.md")
    _s.prompt_text = prompts.POSITIONING_BRIEF_PROMPT.format(
        role_intel=strategy, tailored_resume=tailored, job_description=job_description
    )
    try:
        with _s, console.status("[cyan]Generating positioning brief...[/cyan]", spinner="dots"):
            for chunk in llm.positioning_brief(strategy, tailored, job_description, model, provider=provider):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    pos_brief = _clean_llm_output(_s.output)

    # ---- Cover letter ----
    _vt = f" Candidate's voice and tone: {profile['voice_tone']}" if profile and profile.get("voice_tone") else ""
    _s = _Step("cover_letter", step_logs, output_file="cover_letter.md")
    _s.prompt_text = prompts.COVER_LETTER_PROMPT.format(
        role_intel=strategy, tailored_resume=tailored,
        job_description=job_description, voice_tone_section=_vt,
    )
    try:
        with _s, console.status("[cyan]Writing cover letter...[/cyan]", spinner="dots"):
            for chunk in llm.cover_letter(
                strategy, tailored, job_description, model,
                voice_tone=profile.get("voice_tone") if profile else None,
                provider=provider,
            ):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[yellow]Cover letter generation failed ({e}) — skipping.[/yellow]")
    cover_letter_text = _clean_llm_output(_s.output)

    # ---- Application email + LinkedIn InMail ----
    email_inmail_text = ""
    if profile:
        contact_line = " · ".join(filter(None, [
            profile.get("email", ""), profile.get("phone", ""),
        ]))
        _vt = f" Candidate's voice and tone: {profile['voice_tone']}" if profile.get("voice_tone") else ""
        _s = _Step("email_inmail", step_logs, output_file="email_inmail.md")
        _s.prompt_text = prompts.APPLICATION_EMAIL_PROMPT.format(
            role_intel=strategy, candidate_name=profile.get("name", ""),
            candidate_contact=contact_line, job_title=title,
            company=company, voice_tone_section=_vt,
        )
        try:
            with _s, console.status("[cyan]Drafting email + InMail...[/cyan]", spinner="dots"):
                for chunk in llm.application_email(
                    strategy, profile.get("name", ""), contact_line,
                    title, company, model,
                    voice_tone=profile.get("voice_tone"),
                    provider=provider,
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Email/InMail generation failed ({e}) — skipping.[/yellow]")
        email_inmail_text = _clean_llm_output(_s.output)

    # Also generate a short fit summary for the Notion row.
    _s = _Step("fit_summary", step_logs, output_file="fit_summary.md")
    _s.prompt_text = prompts.FIT_SUMMARY_PROMPT.format(
        resume=base_resume, job_description=job_description
    )
    try:
        with _s, console.status("[cyan]Generating fit summary...[/cyan]", spinner="dots"):
            for chunk in llm.get_fit_summary(base_resume, job_description, model, provider=provider):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    fit_summary = _clean_llm_output(_s.output)

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

    # Build the run log to pass into the package assembler.
    run_finished = _dt.datetime.utcnow()
    _costs = [
        ("gemini_2_flash",   0.10,  0.40),
        ("gpt4o_mini",       0.15,  0.60),
        ("claude_haiku",     0.80,  4.00),
        ("gpt4o",            2.50, 10.00),
        ("claude_sonnet",    3.00, 15.00),
        ("gemini_2_5_pro",   2.50, 15.00),
        ("claude_opus",     15.00, 75.00),
    ]
    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _steps_out = []
        _total_in = _total_out = 0
        for s in step_logs:
            _in = len(_enc.encode(s.get("prompt_text", "")))
            _out = len(_enc.encode(s.get("output_text", "")))
            _total_in += _in
            _total_out += _out
            _steps_out.append({k: v for k, v in s.items() if k not in ("prompt_text", "output_text")} | {"tokens_in": _in, "tokens_out": _out})
        _cost_estimates = {name: round((_total_in * inp + _total_out * out) / 1_000_000, 6) for name, inp, out in _costs}
    except Exception:
        _steps_out = [{k: v for k, v in s.items() if k not in ("prompt_text", "output_text")} for s in step_logs]
        _total_in = _total_out = 0
        _cost_estimates = {}

    run_log = {
        "run_id": run_id,
        "started_at": run_started.isoformat() + "Z",
        "finished_at": run_finished.isoformat() + "Z",
        "duration_seconds": round((run_finished - run_started).total_seconds(), 2),
        "model": model,
        "provider": provider,
        "source_url": source_url or None,
        "job": {"title": title, "company": company},
        "steps": _steps_out,
        "totals": {"tokens_in": _total_in, "tokens_out": _total_out, "total_tokens": _total_in + _total_out},
        "cost_estimates": _cost_estimates,
    }

    # Build the application package folder (md + html + pdf + manifest).
    try:
        with console.status(
            "[cyan]Rendering HTML + PDF and assembling package...[/cyan]",
            spinner="dots",
        ):
            output_root = Path(cfg["output_dir"]).expanduser() if cfg.get("output_dir") else None
            folder = package.assemble(
                job, tailored, fit_summary,
                strategy=strategy or None,
                company_context=company_page_text or None,
                positioning_brief=pos_brief or None,
                cover_letter=cover_letter_text or None,
                email_inmail=email_inmail_text or None,
                job_description=job_description or None,
                generate_docx=cfg.get("generate_docx", False),
                run_log=run_log if cfg.get("generate_run_log", True) else None,
                model=model_arg or None,
                output_root=output_root,
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

    # Token usage display from run_log.
    if run_log["totals"]["total_tokens"] > 0:
        step_lines = []
        for s in run_log["steps"]:
            label = s["name"].replace("_", " ").title()
            note = s.get("note", "")
            if note:
                step_lines.append(f"  {label:<22} {note}")
            else:
                step_lines.append(f"  {label:<22} {s.get('tokens_in', 0):>6,} in + {s.get('tokens_out', 0):>6,} out  [{s.get('duration_seconds', 0):.1f}s]")
        cost_lines = "\n".join(
            f"  {name:<22} ${cost:.4f}"
            for name, cost in run_log["cost_estimates"].items()
        )
        t = run_log["totals"]
        console.print(
            f"\n[dim]Token usage (tiktoken cl100k):\n"
            f"{chr(10).join(step_lines)}\n"
            f"  {'─' * 50}\n"
            f"  {'Total':<22} {t['tokens_in']:>6,} in + {t['tokens_out']:>6,} out = {t['total_tokens']:,}\n"
            f"  Run time: {run_log['duration_seconds']}s  |  Model: {run_log['model']} ({run_log['provider']})\n\n"
            f"  API cost estimate:\n{cost_lines}[/dim]"
        )

    # ATS score hint — extract score from strategy and suggest next steps.
    import re as _re
    _ats_match = _re.search(r"ATS match score.*?(\d{2,3})\s*(?:/\s*100|%|out of)", strategy, flags=_re.IGNORECASE)
    _ats_threshold = int(cfg.get("ats_hint_threshold", 80))
    if _ats_match:
        _ats_score = int(_ats_match.group(1))
        if _ats_score >= _ats_threshold:
            console.print(
                f"\n[dim]ATS score: {_ats_score}/100 — strong match.\n"
                f"Consider:\n"
                f"  applycling critique {job.id:<12} → recruiter review (uses a stronger model)\n"
                f"  applycling refine {job.id:<14} → iterate with your own feedback[/dim]"
            )

    # Critique models staleness check — nudge once every 90 days.
    _reviewed = cfg.get("critique_models_reviewed_at")
    _today = _dt.date.today()
    if not _reviewed:
        # First run — stamp today, no nudge yet.
        storage.save_config({"critique_models_reviewed_at": _today.isoformat()})
    else:
        try:
            _days_since = (_today - _dt.date.fromisoformat(_reviewed)).days
            if _days_since >= 90:
                console.print(
                    f"\n[yellow]Heads up:[/yellow] [dim]It's been {_days_since} days since critique models were last reviewed.\n"
                    f"Consider checking if newer models are available and update [bold]critique_models[/bold] in data/config.json.\n"
                    f"To dismiss this warning: set [bold]\"critique_models_reviewed_at\": \"{_today.isoformat()}\"[/bold] in data/config.json.[/dim]"
                )
        except ValueError:
            storage.save_config({"critique_models_reviewed_at": _today.isoformat()})


# ---------- refine ----------

_ARTIFACT_ALIASES: dict[str, str] = {
    "resume": "resume",
    "cover-letter": "cover_letter",
    "coverletter": "cover_letter",
    "cl": "cover_letter",
    "brief": "brief",
    "positioning-brief": "brief",
    "email": "email",
    "inmail": "email",
    "email-inmail": "email",
}

# Downstream cascade: regenerating X also regenerates these (in order).
_DOWNSTREAM: dict[str, list[str]] = {
    "resume": ["brief", "cover_letter", "email"],
    "cover_letter": ["email"],
    "brief": [],
    "email": [],
}

_VERSIONABLE = {
    "resume.md", "resume.html", "resume.pdf", "resume.docx",
    "cover_letter.md", "cover_letter.html", "cover_letter.pdf", "cover_letter.docx",
    "positioning_brief.md", "email_inmail.md",
}


def _version_artifacts(folder: Path) -> Path:
    """Copy all versionable root files into a v{n}/ snapshot folder. Returns the snapshot path."""
    import shutil
    existing = sorted(
        int(d.name[1:]) for d in folder.iterdir()
        if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
    )
    next_v = (existing[-1] + 1) if existing else 1
    v_folder = folder / f"v{next_v}"
    v_folder.mkdir()
    for fname in _VERSIONABLE:
        src = folder / fname
        if src.exists():
            shutil.copy2(src, v_folder / fname)
    return v_folder


def _parse_refine_only(only_str: str) -> list[str]:
    """Parse --only value into a list of canonical artifact names."""
    if not only_str.strip():
        return []
    result = []
    for part in only_str.split(","):
        key = part.strip().lower()
        canonical = _ARTIFACT_ALIASES.get(key)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


@main.command()
@click.argument("job_id")
@click.option("--feedback", "-f", default="", help="What to change (required if not prompted).")
@click.option(
    "--only", default="",
    help="Comma-separated artifacts to regenerate: resume, cover-letter, brief, email. "
         "Default: all that exist. No cascade when --only is used unless --cascade is also passed.",
)
@click.option("--cascade", "cascade", is_flag=True, help="When used with --only, also regenerate downstream artifacts.")
@click.option("--model", "model_arg", default="", help="Override model for this run.")
@click.option("--provider", "provider_arg", default="", help="Override provider for this run.")
def refine(job_id: str, feedback: str, only: str, cascade: bool, model_arg: str, provider_arg: str) -> None:
    """Iterate on an existing application package with feedback."""
    cfg = _require_config()
    model = model_arg or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = provider_arg or cfg.get("provider", "ollama")
    profile = storage.load_profile()

    store = get_store()
    try:
        job = store.load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if not job.package_folder:
        console.print("[red]No package folder recorded for this job.[/red] Run `applycling add` first.")
        sys.exit(1)

    folder = Path(job.package_folder)
    if not folder.exists():
        console.print(f"[red]Package folder not found:[/red] {folder}")
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[bold]Refining[/bold] [cyan]{job.company}[/cyan] — {job.title}  [dim]({job_id})[/dim]",
            style="cyan",
        )
    )

    # Load existing artifacts.
    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    existing_resume = _read("resume.md")
    existing_cover_letter = _read("cover_letter.md")
    existing_brief = _read("positioning_brief.md")
    existing_email = _read("email_inmail.md")
    strategy = _read("strategy.md")
    # JD: prefer dedicated file, fall back to strategy.md for older packages.
    job_description = _read("job_description.md") or strategy

    if not existing_resume:
        console.print("[red]resume.md not found in package folder.[/red]")
        sys.exit(1)
    if not job_description:
        console.print("[red]No job description or strategy found in package folder.[/red]")
        sys.exit(1)

    # Collect feedback.
    if not feedback:
        feedback = Prompt.ask("\nWhat should change? (describe the feedback)")
    if not feedback.strip():
        console.print("[yellow]No feedback provided — nothing to refine.[/yellow]")
        sys.exit(0)

    # Determine which artifacts to regenerate.
    explicit = _parse_refine_only(only)
    if not explicit:
        # Default: all artifacts that exist.
        if existing_resume:
            explicit.append("resume")
        if existing_cover_letter:
            explicit.append("cover_letter")
        if existing_brief:
            explicit.append("brief")
        if existing_email:
            explicit.append("email")

    # Apply cascade: always when no --only; only when --cascade is explicitly passed with --only.
    in_scope: list[str] = list(explicit)
    if not only or cascade:
        for artifact in list(explicit):
            for downstream in _DOWNSTREAM.get(artifact, []):
                if downstream not in in_scope:
                    # Only add downstream if the file exists.
                    fname_map = {"cover_letter": "cover_letter.md", "brief": "positioning_brief.md", "email": "email_inmail.md"}
                    if (folder / fname_map.get(downstream, f"{downstream}.md")).exists():
                        in_scope.append(downstream)

    console.print(f"\n[dim]Artifacts in scope: {', '.join(in_scope)}[/dim]")

    # Snapshot existing files to v{n}/ before writing.
    v_folder = _version_artifacts(folder)
    console.print(f"[dim]Archived previous version to {v_folder.name}/[/dim]\n")

    step_logs: list[dict] = []
    run_started = _dt.datetime.utcnow()

    # ---- Refine resume ----
    refined_resume_body = ""
    if "resume" in in_scope:
        _s = _Step("refine_resume", step_logs, output_file="resume.md")
        _s.prompt_text = prompts.REFINE_RESUME_PROMPT.format(
            feedback=feedback, resume=existing_resume, job_description=job_description
        )
        try:
            with _s, console.status("[cyan]Refining resume...[/cyan]", spinner="dots"):
                for chunk in llm.refine_resume(existing_resume, job_description, feedback, model, provider=provider):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)
        refined_body = _clean_llm_output(_s.output)

        # Format pass.
        _sf = _Step("format_resume_refine", step_logs, output_file="resume.md")
        _sf.prompt_text = prompts.FORMAT_RESUME_PROMPT.format(resume=refined_body)
        try:
            with _sf, console.status("[cyan]Formatting refined resume...[/cyan]", spinner="dots"):
                for chunk in llm.format_resume(refined_body, model, provider=provider):
                    _sf.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Format pass failed ({e}) — using unformatted output.[/yellow]")
        formatted_body = _clean_llm_output(_sf.output) or refined_body

        # Re-attach profile header (strip any existing header from the stored resume.md first).
        import re as _re
        # The stored resume.md has the full assembled resume including profile header.
        # Extract just the body (everything after ## PROFILE or first ## section that isn't PROFILE).
        body_only = formatted_body
        resume_sections: list[str] = []
        if profile:
            resume_sections.append(_profile_header_markdown(profile))
        # Check if original had a PROFILE section and preserve it.
        profile_match = _re.search(r"## PROFILE\s*\n(.*?)(?=\n## |\Z)", existing_resume, flags=_re.DOTALL)
        if profile_match:
            profile_text = profile_match.group(1).strip()
            resume_sections.append(f"## PROFILE\n\n{profile_text}")
        resume_sections.append(body_only)
        refined_resume_full = "\n\n".join(resume_sections)
        refined_resume_body = refined_resume_full

        # Write resume.md.
        (folder / "resume.md").write_text(refined_resume_full, encoding="utf-8")

        # Re-render HTML + PDF.
        try:
            with console.status("[cyan]Re-rendering resume HTML + PDF...[/cyan]", spinner="dots"):
                render.render_resume(
                    refined_resume_full, folder,
                    title=f"{job.title} — {job.company}",
                )
            if cfg.get("generate_docx", False):
                render.markdown_to_docx(refined_resume_full, folder / "resume.docx")
        except Exception as e:
            console.print(f"[yellow]Render failed ({e}) — resume.md updated but HTML/PDF may be stale.[/yellow]")

    # ---- Refine positioning brief ----
    if "brief" in in_scope and existing_brief:
        current_resume = refined_resume_body or existing_resume
        _s = _Step("refine_brief", step_logs, output_file="positioning_brief.md")
        _s.prompt_text = prompts.REFINE_POSITIONING_BRIEF_PROMPT.format(
            feedback=feedback, resume=current_resume, brief=existing_brief, role_intel=strategy
        )
        try:
            with _s, console.status("[cyan]Updating positioning brief...[/cyan]", spinner="dots"):
                for chunk in llm.refine_positioning_brief(
                    existing_brief, current_resume, strategy, feedback, model, provider=provider
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Brief update failed ({e}) — skipping.[/yellow]")
        if _s.output.strip():
            refined_brief = _clean_llm_output(_s.output)
            (folder / "positioning_brief.md").write_text(
                f"# Positioning brief — {job.title} @ {job.company}\n\n{refined_brief}\n",
                encoding="utf-8",
            )

    # ---- Refine cover letter ----
    if "cover_letter" in in_scope and existing_cover_letter:
        _s = _Step("refine_cover_letter", step_logs, output_file="cover_letter.md")
        _s.prompt_text = prompts.REFINE_COVER_LETTER_PROMPT.format(
            feedback=feedback, cover_letter=existing_cover_letter, role_intel=strategy
        )
        try:
            with _s, console.status("[cyan]Refining cover letter...[/cyan]", spinner="dots"):
                for chunk in llm.refine_cover_letter(
                    existing_cover_letter, strategy, feedback, model, provider=provider
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Cover letter refinement failed ({e}) — skipping.[/yellow]")
        if _s.output.strip():
            refined_cl = _clean_llm_output(_s.output)
            cl_md = f"# Cover Letter — {job.title} @ {job.company}\n\n{refined_cl}\n"
            (folder / "cover_letter.md").write_text(cl_md, encoding="utf-8")
            try:
                with console.status("[cyan]Re-rendering cover letter HTML + PDF...[/cyan]", spinner="dots"):
                    cl_html = render.markdown_to_html(cl_md, title=f"Cover Letter — {job.title}")
                    cl_html_path = folder / "cover_letter.html"
                    cl_html_path.write_text(cl_html, encoding="utf-8")
                    render.html_to_pdf(cl_html_path, folder / "cover_letter.pdf")
                if cfg.get("generate_docx", False):
                    render.markdown_to_docx(cl_md, folder / "cover_letter.docx")
            except Exception as e:
                console.print(f"[yellow]Cover letter render failed ({e}) — .md updated but HTML/PDF may be stale.[/yellow]")

    # ---- Refine email + InMail ----
    if "email" in in_scope and existing_email:
        _s = _Step("refine_email", step_logs, output_file="email_inmail.md")
        _s.prompt_text = prompts.REFINE_EMAIL_INMAIL_PROMPT.format(
            feedback=feedback, email_inmail=existing_email, role_intel=strategy
        )
        try:
            with _s, console.status("[cyan]Updating email + InMail...[/cyan]", spinner="dots"):
                for chunk in llm.refine_email_inmail(
                    existing_email, strategy, feedback, model, provider=provider
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Email/InMail refinement failed ({e}) — skipping.[/yellow]")
        if _s.output.strip():
            refined_email = _clean_llm_output(_s.output)
            (folder / "email_inmail.md").write_text(
                f"# Outreach — {job.title} @ {job.company}\n\n{refined_email}\n",
                encoding="utf-8",
            )

    run_finished = _dt.datetime.utcnow()

    # Token usage display.
    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _total_in = sum(len(_enc.encode(s.get("prompt_text", ""))) for s in step_logs)
        _total_out = sum(len(_enc.encode(s.get("output_text", ""))) for s in step_logs)
        console.print(
            f"\n[dim]Refine token usage: {_total_in:,} in + {_total_out:,} out = {_total_in + _total_out:,}  "
            f"[{round((run_finished - run_started).total_seconds(), 1)}s][/dim]"
        )
    except Exception:
        pass

    console.print(f"\n[green]Refined:[/green] [bold]{folder}[/bold]")
    console.print(f"[dim]Previous version archived to [bold]{v_folder.name}/[/bold][/dim]")


# ---------- critique ----------

# Strongest model per provider — critique warrants maximum judgment.
_CRITIQUE_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-6",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
}


@main.command()
@click.argument("job_id")
@click.option("--model", "model_arg", default="", help="Override model (default: strongest for your provider).")
@click.option("--provider", "provider_arg", default="", help="Override provider.")
def critique(job_id: str, model_arg: str, provider_arg: str) -> None:
    """Senior recruiter review of a complete application package."""
    cfg = _require_config()
    provider = provider_arg or cfg.get("provider", "ollama")
    # Default to strongest model for the provider; fall back to configured model.
    # config.json "critique_models" overrides the hardcoded dict per provider.
    _effective_models = {**_CRITIQUE_MODELS, **cfg.get("critique_models", {})}
    strongest = _effective_models.get(provider)
    model = model_arg or strongest or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    if not model_arg and not strongest:
        console.print(f"[dim]No stronger model known for {provider} — using configured model: {model}[/dim]")

    store = get_store()
    try:
        job = store.load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if not job.package_folder:
        console.print("[red]No package folder recorded for this job.[/red] Run `applycling add` first.")
        sys.exit(1)

    folder = Path(job.package_folder)
    if not folder.exists():
        console.print(f"[red]Package folder not found:[/red] {folder}")
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[bold]Critique[/bold] [cyan]{job.company}[/cyan] — {job.title}  [dim]({job_id})[/dim]\n"
            f"[dim]Model: {model} ({provider})[/dim]",
            style="cyan",
        )
    )

    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    resume = _read("resume.md")
    cover_letter_text = _read("cover_letter.md")
    strategy = _read("strategy.md")
    positioning_brief_text = _read("positioning_brief.md")
    job_description = _read("job_description.md") or strategy

    if not resume:
        console.print("[red]resume.md not found in package folder.[/red]")
        sys.exit(1)
    if not job_description:
        console.print("[red]No job description or strategy found in package folder.[/red]")
        sys.exit(1)

    step_logs: list[dict] = []
    _s = _Step("critique", step_logs, output_file="critique.md")
    _s.prompt_text = prompts.CRITIQUE_PROMPT.format(
        job_description=job_description,
        resume=resume,
        cover_letter=cover_letter_text or "(not provided)",
        role_intel=strategy,
        positioning_brief=positioning_brief_text or "(not provided)",
    )
    try:
        with _s, console.status("[cyan]Running recruiter critique...[/cyan]", spinner="dots"):
            for chunk in llm.critique(
                job_description, resume, strategy, model,
                cover_letter=cover_letter_text,
                positioning_brief=positioning_brief_text,
                provider=provider,
            ):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    critique_text = _clean_llm_output(_s.output)
    if not critique_text:
        console.print("[yellow]Critique came back empty.[/yellow]")
        sys.exit(1)

    out_path = folder / "critique.md"
    out_path.write_text(
        f"# Critique — {job.title} @ {job.company}\n\n{critique_text}\n",
        encoding="utf-8",
    )

    console.print()
    console.print(Panel(critique_text, title="[bold]Recruiter Critique[/bold]", style="magenta"))
    console.print(f"\n[green]Saved:[/green] {out_path}")

    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _in = len(_enc.encode(_s.prompt_text))
        _out = len(_enc.encode(_s.output))
        console.print(f"[dim]Tokens: {_in:,} in + {_out:,} out  [{_s.duration}s][/dim]")
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
