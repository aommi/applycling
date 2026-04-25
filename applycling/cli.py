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

from . import llm, notion_connect, package, pdf_import, render, storage
from .skills import load_skill
from .text_utils import clean_llm_output as _clean_llm_output
from .tracker import STATUSES, Job, TrackerError, get_store

console = Console()


def _utcnow() -> _dt.datetime:
    """Naive UTC now via non-deprecated API (replaces datetime.utcnow())."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

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
        self._started = _utcnow()
        return self

    def collect(self, chunk: str) -> None:
        self._parts.append(chunk)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        finished = _utcnow()
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

    def _step_applicant_profile():
        console.print("\n[bold]Step 6 — Application details[/bold] [dim](injected into cover letters, emails, and briefs)[/dim]")
        existing = storage.load_applicant_profile()

        result: dict = {}
        skipped: list[str] = []

        def _show_current(key: str, label: str, formatter=str) -> None:
            value = existing.get(key)
            if value not in (None, "", []):
                console.print(f"  [dim]current {label}: {formatter(value)}[/dim]")

        # --- work_auth ---
        console.print()
        _show_current("work_auth", "work auth")
        val = Prompt.ask(
            'Work authorization (e.g. "Canadian PR", "needs H1B") — press Enter to skip',
            default="",
            show_default=False,
        ).strip()
        if val:
            console.print(f"  [dim]got it — work auth: {val}. ✓[/dim]")
            result["work_auth"] = val
        else:
            console.print("  [dim]skipped. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["work_auth"] = ""
            skipped.append("work auth")

        # --- sponsorship_needed ---
        console.print()
        existing_sponsor = existing.get("sponsorship_needed")
        if existing_sponsor is not None:
            console.print(f"  [dim]current sponsorship needed: {'yes' if existing_sponsor else 'no'}[/dim]")
        val = Prompt.ask(
            "Sponsorship needed? [y/n] — press Enter to skip",
            default="",
            show_default=False,
        ).strip().lower()
        if val in ("y", "yes"):
            console.print("  [dim]got it — sponsorship needed: yes. ✓[/dim]")
            result["sponsorship_needed"] = True
        elif val in ("n", "no"):
            console.print("  [dim]got it — sponsorship needed: no. ✓[/dim]")
            result["sponsorship_needed"] = False
        else:
            console.print("  [dim]skipped. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["sponsorship_needed"] = None
            skipped.append("sponsorship")

        # --- relocation ---
        console.print()
        existing_reloc = existing.get("relocation")
        if existing_reloc is not None:
            console.print(f"  [dim]current open to relocation: {'yes' if existing_reloc else 'no'}[/dim]")
        val = Prompt.ask(
            "Open to relocation? [y/n] — press Enter to skip",
            default="",
            show_default=False,
        ).strip().lower()
        if val in ("y", "yes"):
            _show_current("relocation_cities", "preferred cities", lambda cities: ", ".join(cities))
            cities_input = Prompt.ask(
                "Preferred cities (comma-separated) — press Enter to skip",
                default="",
                show_default=False,
            ).strip()
            relocation_cities = [c.strip() for c in cities_input.split(",") if c.strip()]
            if relocation_cities:
                console.print(f"  [dim]got it — open to relocation in: {', '.join(relocation_cities)}. ✓[/dim]")
                result["relocation_cities"] = relocation_cities
            else:
                console.print("  [dim]got it — open to relocation (cities tbd). ✓[/dim]")
                result["relocation_cities"] = []
            result["relocation"] = True
        elif val in ("n", "no"):
            console.print("  [dim]got it — not open to relocation. ✓[/dim]")
            result["relocation"] = False
            result["relocation_cities"] = []  # clear any stale cities from a previous yes
        else:
            console.print("  [dim]skipped. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["relocation"] = None
            result["relocation_cities"] = []
            skipped.append("relocation")

        # --- remote_preference (always filled; default: flexible) ---
        console.print()
        remote_default = existing.get("remote_preference", "flexible")
        remote_preference = _pick(
            "Remote preference",
            ["flexible", "remote", "hybrid", "on-site", _BACK],
            default=remote_default,
        )
        if remote_preference == _BACK:
            return _BACK
        is_default_remote = remote_preference == "flexible" and not existing.get("remote_preference")
        if is_default_remote:
            console.print(f"  [dim]got it — remote preference: {remote_preference} (default). ✓[/dim]")
        else:
            console.print(f"  [dim]got it — remote preference: {remote_preference}. ✓[/dim]")
        result["remote_preference"] = remote_preference

        # --- comp_expectation (single free-text; migrates old structured dict) ---
        console.print()
        existing_comp = existing.get("comp_expectation", "")
        if isinstance(existing_comp, dict):
            comp_parts = []
            if existing_comp.get("min"):
                comp_parts.append(f"min {existing_comp['min']}")
            if existing_comp.get("target"):
                comp_parts.append(f"target {existing_comp['target']}")
            currency = existing_comp.get("currency", "")
            existing_comp_str = ", ".join(comp_parts) + (f" {currency}" if currency else "")
        else:
            existing_comp_str = existing_comp or ""
        if existing_comp_str:
            console.print(f"  [dim]current comp expectations: {existing_comp_str}[/dim]")
        val = Prompt.ask(
            "Compensation expectations (e.g. $150-200k CAD) — press Enter to skip",
            default="",
            show_default=False,
        ).strip()
        if val:
            console.print(f"  [dim]got it — comp expectations: {val}. ✓[/dim]")
            result["comp_expectation"] = val
        else:
            console.print("  [dim]skipped for now. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["comp_expectation"] = ""
            skipped.append("comp expectations")

        # --- notice_period ---
        console.print()
        _show_current("notice_period", "notice period")
        val = Prompt.ask(
            "Notice period (e.g. 2 weeks, immediate) — press Enter to skip",
            default="",
            show_default=False,
        ).strip()
        if val:
            console.print(f"  [dim]got it — notice period: {val}. ✓[/dim]")
            result["notice_period"] = val
        else:
            console.print("  [dim]skipped. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["notice_period"] = ""
            skipped.append("notice period")

        # --- earliest_start_date ---
        console.print()
        _show_current("earliest_start_date", "earliest start")
        val = Prompt.ask(
            "Earliest start date — press Enter to skip",
            default="",
            show_default=False,
        ).strip()
        if val:
            console.print(f"  [dim]got it — earliest start: {val}. ✓[/dim]")
            result["earliest_start_date"] = val
        else:
            console.print("  [dim]skipped. you can add this anytime with [bold]applycling setup[/bold].[/dim]")
            result["earliest_start_date"] = ""
            skipped.append("earliest start")

        # --- Summary block ---
        console.print()
        summary_lines = ["[green]applicant profile saved to data/applicant_profile.json:[/green]"]
        field_labels = [
            ("work_auth", "work auth"),
            ("sponsorship_needed", "sponsorship needed"),
            ("relocation", "open to relocation"),
            ("remote_preference", "remote preference"),
            ("comp_expectation", "comp expectations"),
            ("notice_period", "notice period"),
            ("earliest_start_date", "earliest start"),
        ]
        for key, label in field_labels:
            if key not in result:
                continue
            v = result[key]
            if v in (None, "", []):
                continue
            if key == "relocation" and result.get("relocation_cities"):
                summary_lines.append(f"- {label}: yes ({', '.join(result['relocation_cities'])})")
            elif isinstance(v, bool):
                summary_lines.append(f"- {label}: {'yes' if v else 'no'}")
            else:
                summary_lines.append(f"- {label}: {v}")
        if skipped:
            summary_lines.append(
                f"[dim]- skipped: {', '.join(skipped)} "
                f"(run [bold]applycling setup[/bold] anytime to add)[/dim]"
            )
        console.print(Panel("\n".join(summary_lines), style="green"))

        back = _pick("Continue?", ["continue", _BACK], default="continue")
        if back == _BACK:
            return _BACK
        return result

    def _step_linkedin():
        console.print("\n[bold]Step 7 — LinkedIn profile[/bold] [dim](optional, zero tokens)[/dim]")
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

    while step <= 6:
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
            result = _step_applicant_profile()
            if result == _BACK:
                step -= 1
            else:
                storage.save_applicant_profile(result)
                step += 1
        elif step == 6:
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
@click.option("--non-interactive", "non_interactive", is_flag=True, help="Alias for --async: skip all prompts, auto-resolve gates.")
@click.option("--url", "url_arg", default="", help="Job posting URL — skips the URL prompt.")
@click.option("--model", "model_arg", default="", help="Override the model from config (e.g. gemma4:27b, claude-haiku-4-5-20251001).")
@click.option("--provider", "provider_arg", default="", help="Override the provider from config (ollama, anthropic, google).")
def add(async_mode: bool, non_interactive: bool, url_arg: str, model_arg: str, provider_arg: str) -> None:
    """Add a job: tailor a resume + assemble an application package."""
    from . import pipeline as _pipeline

    cfg = _require_config()
    review_mode = cfg.get("review_mode", "interactive")
    if async_mode or non_interactive:
        review_mode = "async"
    _require_resume()  # fail-fast if resume is missing
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

    source_url = url_arg or (
        "" if review_mode == "async" else Prompt.ask("Job posting URL (leave blank to enter details manually)", default="")
    )
    title = company = job_description = ""
    company_url = ""

    if source_url:
        from . import scraper
        try:
            with console.status("[cyan]Fetching job posting...[/cyan]", spinner="dots"):
                posting, _scrape_tokens = scraper.fetch_job_posting(source_url, model, provider=provider)
            if not _scrape_tokens[0]:
                console.print("[dim]Extracted from structured data — no LLM call needed.[/dim]")
            title = posting.title
            company = posting.company
            job_description = posting.description
            company_url = posting.company_url
            console.print(f"[green]Fetched:[/green] [bold]{title}[/bold] @ [bold]{company}[/bold]")
            if review_mode != "async":
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
        if review_mode == "async":
            console.print("[red]--non-interactive/--async requires --url. No URL provided.[/red]")
            sys.exit(1)
        title = Prompt.ask("Job title")
        company = Prompt.ask("Company name")
        source_url = Prompt.ask("Source URL (optional)", default="")
        company_url = Prompt.ask("Company page URL (optional)", default="")
        job_description = _read_multiline("Paste the job description below (end with --- on its own line):")

    if not job_description:
        console.print("[red]Empty job description — aborting.[/red]")
        sys.exit(1)

    want_summary = True if review_mode == "async" else Prompt.ask(
        "Include a profile summary section?", choices=["y", "n"], default="y"
    ) == "y"

    if stories:
        console.print("[dim]Stories file found — will be considered during tailoring.[/dim]")

    if company_url:
        with console.status("[cyan]Fetching company page...[/cyan]", spinner="dots"):
            pass  # pipeline.run_add handles the actual fetch

    # ---- Build pipeline context ----
    ctx = _pipeline.PipelineContext(
        data_dir=storage.DATA_DIR,
        output_dir=Path(cfg["output_dir"]).expanduser() if cfg.get("output_dir") else Path(storage.DATA_DIR).parent / "output",
        profile=profile or {},
        resume=storage.load_resume(),
        stories=stories or "",
        linkedin_profile=linkedin_profile,
        config=cfg,
        model=model,
        provider=provider,
        tracker_store=get_store(),
    )

    # ---- Define callbacks for rich-console rendering ----
    def _on_status(msg: str) -> None:
        pass  # Status shown via console.status() inside run_add; suppress here

    def _on_gate(content: str) -> "str | None":
        """Interactive gate: show strategy and let user override."""
        import re as _re
        console.print(Panel(content, title="[bold]Role Intel[/bold]", style="cyan"))
        if review_mode != "interactive":
            console.print("[dim]Async mode — auto-proceeding.[/dim]")
            return None
        niche_match = _re.search(r"## Identified niche\s*\n(.+)", content)
        niche_text = niche_match.group(1).strip() if niche_match else "see above"
        console.print(f"\n[bold]Angle:[/bold] {niche_text}")
        angle_ok = Prompt.ask("Does this angle feel right, or do you want to lead with something else?", default="looks good")
        override = content
        if angle_ok.lower() not in ("looks good", "yes", "y", "good", ""):
            override += f"\n\n## Candidate override\nLead with this angle instead: {angle_ok}\n"

        gaps_match = _re.search(r"## Tooling or domain gaps\s*\n([\s\S]*?)(?=\n##|$)", content)
        if gaps_match and gaps_match.group(1).strip() and "no gap" not in gaps_match.group(1).lower():
            console.print(f"\n[bold]Gaps identified:[/bold]\n{gaps_match.group(1).strip()}")
            gap_action = Prompt.ask("How to handle gaps? (bridge / deprioritise / other)", default="bridge")
            override += f"\n\n## Gap handling\nCandidate chose: {gap_action}\n"

        if Prompt.ask("Proceed to resume tailoring?", choices=["y", "edit"], default="y") == "edit":
            override = _read_multiline("Paste your edited strategy:")
        return override if override != content else None

    # ---- Run the pipeline ----
    console.print()
    try:
        with console.status("[cyan]Running pipeline...[/cyan]", spinner="dots"):
            result = _pipeline.run_add(
                job_url=source_url or None,
                job_title=title,
                job_company=company,
                job_description=job_description,
                context=ctx,
                company_url=company_url or None,
                on_status=_on_status,
                on_gate=_on_gate,
                want_summary=want_summary,
                render_pdf=True,
            )
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    # ---- Persist to disk ----
    output_root = Path(cfg["output_dir"]).expanduser() if cfg.get("output_dir") else None
    try:
        with console.status("[cyan]Rendering HTML + PDF and assembling package...[/cyan]", spinner="dots"):
            folder = _pipeline.persist_add_result(
                result,
                output_root=output_root,
                generate_docx=cfg.get("generate_docx", False),
                generate_run_log=cfg.get("generate_run_log", True),
            )
    except Exception as e:
        console.print(f"[red]Package assembly failed:[/red] {e}")
        sys.exit(1)

    # ---- Bug fix (tracker timing): update package_folder AFTER folder exists ----
    store = get_store()
    try:
        store.update_job(result.job.id, package_folder=str(folder))
    except TrackerError as e:
        console.print(f"[yellow]Saved package but failed to record folder path:[/yellow] {e}")

    # ---- Display results ----
    job = result.job
    fit_summary = result.fit_summary
    strategy = result.strategy or ""

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

    # Token usage display — token costs computed by persist_add_result already.
    totals = result.run.total_tokens()
    if totals["total_tokens"] > 0:
        step_lines = []
        for s in result.run.steps:
            label = s.name.replace("_", " ").title()
            step_lines.append(
                f"  {label:<22} {s.tokens_in:>6,} in + {s.tokens_out:>6,} out  [{s.duration_seconds():.1f}s]"
            )
        _costs = [
            ("gemini_2_flash",   0.10,  0.40),
            ("gpt4o_mini",       0.15,  0.60),
            ("claude_haiku",     0.80,  4.00),
            ("gpt4o",            2.50, 10.00),
            ("claude_sonnet",    3.00, 15.00),
            ("gemini_2_5_pro",   2.50, 15.00),
            ("claude_opus",     15.00, 75.00),
        ]
        cost_lines = "\n".join(
            f"  {name:<22} ${round((totals['tokens_in'] * inp + totals['tokens_out'] * out) / 1_000_000, 6):.4f}"
            for name, inp, out in _costs
        )
        console.print(
            f"\n[dim]Token usage (tiktoken cl100k):\n"
            f"{chr(10).join(step_lines)}\n"
            f"  {'─' * 50}\n"
            f"  {'Total':<22} {totals['tokens_in']:>6,} in + {totals['tokens_out']:>6,} out = {totals['total_tokens']:,}\n"
            f"  Run time: {result.run.duration_seconds()}s  |  Model: {model} ({provider})\n\n"
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
    run_started = _utcnow()

    # ---- Refine resume ----
    refined_resume_body = ""
    if "resume" in in_scope:
        _s = _Step("refine_resume", step_logs, output_file="resume.md")
        _s.prompt_text = load_skill("refine_resume").render(
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
        _sf.prompt_text = load_skill("format_resume").render(resume=refined_body)
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
        _s.prompt_text = load_skill("refine_positioning_brief").render(
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
        _s.prompt_text = load_skill("refine_cover_letter").render(
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
        _s.prompt_text = load_skill("refine_email_inmail").render(
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

    run_finished = _utcnow()

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


# ---------- prep ----------

_PREP_STAGES = ("recruiter", "hiring-manager", "technical", "executive")
_PREP_STAGE_LABELS = {
    "recruiter": "recruiter screen",
    "hiring-manager": "hiring manager deep-dive",
    "technical": "technical",
    "executive": "executive",
}


_INTEL_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
_INTEL_TEXT_EXTS = {".md", ".txt", ".text"}


def _read_intel_folder(
    folder: Path,
    vision_model: str = "",
    vision_provider: str = "",
) -> tuple[str, list[str]]:
    """Read all files from intel/ subfolder.

    Returns (combined_text, warnings). Warnings are shown to the user for
    unreadable or unsupported files — nothing fails silently.

    If vision_model is set, image files are processed via the vision LLM.
    Extraction caches are stored in intel/.cache/ to keep the intel folder clean.
    """
    intel_dir = folder / "intel"
    if not intel_dir.exists():
        return "", []

    # Cache lives in intel/.cache/ — hidden from the user, keeps intel/ clean.
    cache_dir = intel_dir / ".cache"

    parts: list[str] = []
    warnings: list[str] = []

    for f in sorted(intel_dir.iterdir()):
        if f.is_dir():
            continue
        ext = f.suffix.lower()

        if ext in _INTEL_IMAGE_EXTS:
            # Check for cached extraction first (new location: .cache/).
            cache_path = cache_dir / f"{f.stem}.extracted.md"
            # Also check old location alongside image for backwards compat.
            old_cache_path = intel_dir / f"{f.stem}.extracted.md"
            if not cache_path.exists() and old_cache_path.exists():
                # Migrate old cache to new location.
                cache_dir.mkdir(exist_ok=True)
                cache_path.write_text(old_cache_path.read_text(encoding="utf-8"), encoding="utf-8")
                old_cache_path.unlink()

            if cache_path.exists() and cache_path.stat().st_mtime >= f.stat().st_mtime:
                try:
                    cached = cache_path.read_text(encoding="utf-8").strip()
                    if cached:
                        parts.append(f"--- {f.name} (cached) ---\n{cached}")
                        continue
                except Exception:
                    pass  # Fall through to re-extract.

            if vision_model:
                try:
                    text = llm.extract_image_text(f, vision_model, vision_provider)
                    if text.strip():
                        parts.append(f"--- {f.name} (extracted via {vision_model}) ---\n{text.strip()}")
                        # Cache the extraction in .cache/.
                        cache_dir.mkdir(exist_ok=True)
                        cache_path.write_text(text.strip(), encoding="utf-8")
                    else:
                        warnings.append(f"{f.name}: vision model returned empty text.")
                except llm.LLMError as e:
                    warnings.append(f"{f.name}: vision extraction failed ({e}).")
            else:
                warnings.append(
                    f"{f.name}: image file skipped — set intel_vision_model and intel_vision_provider "
                    f"in data/config.json to enable image extraction."
                )
        elif ext == ".pdf":
            try:
                from . import pdf_import
                text = pdf_import.extract_text(f)
                if text.strip():
                    parts.append(f"--- {f.name} ---\n{text.strip()}")
                elif vision_model:
                    # Text extraction empty — try vision as fallback for scanned PDFs.
                    try:
                        # Convert first page to image not feasible without heavy deps,
                        # so just warn with a more specific message.
                        warnings.append(
                            f"{f.name}: PDF appears to be image-only. "
                            f"Vision extraction for PDFs is not yet supported — "
                            f"screenshot the relevant pages and drop them in intel/ as .png/.jpg."
                        )
                    except Exception:
                        pass
                else:
                    warnings.append(f"{f.name}: PDF extracted but appears to be empty or image-only — try exporting as text.")
            except Exception as e:
                warnings.append(f"{f.name}: could not read PDF ({e}).")
        elif ext in _INTEL_TEXT_EXTS:
            try:
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"--- {f.name} ---\n{text}")
                else:
                    warnings.append(f"{f.name}: file is empty.")
            except Exception as e:
                warnings.append(f"{f.name}: could not read file ({e}).")
        else:
            warnings.append(f"{f.name}: unsupported file type ({ext}) — supported: .pdf, .md, .txt, images (with vision model).")

    return "\n\n".join(parts), warnings


@main.command()
@click.argument("job_id")
@click.option(
    "--stage", "stage_arg", default="",
    help=f"Focus on one stage: {', '.join(_PREP_STAGES)}. Default: all stages.",
)
@click.option("--model", "model_arg", default="", help="Override model for this run.")
@click.option("--provider", "provider_arg", default="", help="Override provider.")
def prep(job_id: str, stage_arg: str, model_arg: str, provider_arg: str) -> None:
    """Generate stage-specific interview prep for a job."""
    cfg = _require_config()
    model = model_arg or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = provider_arg or cfg.get("provider", "ollama")

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

    # Resolve stages.
    if stage_arg:
        key = stage_arg.lower().strip()
        if key not in _PREP_STAGE_LABELS:
            console.print(f"[red]Unknown stage '{stage_arg}'.[/red] Valid: {', '.join(_PREP_STAGES)}")
            sys.exit(1)
        stages_str = _PREP_STAGE_LABELS[key]
    else:
        stages_str = ", ".join(_PREP_STAGE_LABELS.values())

    console.print(
        Panel.fit(
            f"[bold]Interview Prep[/bold] [cyan]{job.company}[/cyan] — {job.title}  [dim]({job_id})[/dim]\n"
            f"[dim]Stages: {stages_str}[/dim]",
            style="cyan",
        )
    )

    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    resume = _read("resume.md")
    strategy = _read("strategy.md")
    positioning_brief_text = _read("positioning_brief.md")
    job_description = _read("job_description.md") or strategy

    if not resume:
        console.print("[red]resume.md not found in package folder.[/red]")
        sys.exit(1)
    if not job_description:
        console.print("[red]No job description or strategy found in package folder.[/red]")
        sys.exit(1)

    # Collect intel: intel/ folder + Notion page notes.
    intel_parts: list[str] = []
    _vision_model = cfg.get("intel_vision_model", "")
    _vision_provider = cfg.get("intel_vision_provider", provider) if _vision_model else ""
    intel_folder_text, intel_warnings = _read_intel_folder(
        folder, vision_model=_vision_model, vision_provider=_vision_provider,
    )

    # Print warnings first so they stand out.
    for w in intel_warnings:
        console.print(f"[yellow]Intel warning:[/yellow] {w}")

    # Build a context summary table.
    console.print("\n[dim]Context loaded for prep:[/dim]")
    console.print(f"[dim]  {'resume.md':<28} ✓[/dim]")
    console.print(f"[dim]  {'job description':<28} ✓[/dim]")
    console.print(f"[dim]  {'role intel / strategy':<28} {'✓' if strategy else '—'}[/dim]")
    console.print(f"[dim]  {'positioning brief':<28} {'✓' if positioning_brief_text else '—'}[/dim]")

    intel_dir = folder / "intel"
    intel_files = [
        f for f in sorted(intel_dir.iterdir())
        if not f.is_dir()
    ] if intel_dir.exists() else []
    _processable_exts = {".pdf"} | _INTEL_TEXT_EXTS | (_INTEL_IMAGE_EXTS if _vision_model else set())
    loaded_files = [f for f in intel_files if f.suffix.lower() in _processable_exts]
    skipped_files = [f for f in intel_files if f not in loaded_files]

    if _vision_model:
        console.print(f"[dim]  {'vision model':<28} {_vision_model} ({_vision_provider})[/dim]")

    if loaded_files:
        for f in loaded_files:
            label = "intel/" + f.name
            if f.suffix.lower() in _INTEL_IMAGE_EXTS:
                cache_path = intel_dir / ".cache" / f"{f.stem}.extracted.md"
                note = " (cached)" if cache_path.exists() and cache_path.stat().st_mtime >= f.stat().st_mtime else " (vision)"
            else:
                note = ""
            console.print(f"[dim]  {label:<28} ✓{note}[/dim]")
    else:
        console.print(f"[dim]  {'intel/ (empty)':<28} — tip: drop .pdf/.md/.txt files here for richer prep[/dim]")
    for f in skipped_files:
        console.print(f"[dim]  {'intel/' + f.name:<28} ✗ (skipped — see warning above)[/dim]")

    notion_notes = store.load_job_notes(job_id)
    console.print(f"[dim]  {'Notion page notes':<28} {'✓' if notion_notes else '— (not connected or empty)'}[/dim]")
    console.print()

    if intel_folder_text:
        intel_parts.append(intel_folder_text)
    if notion_notes:
        intel_parts.append(f"--- Notion page notes ---\n{notion_notes}")

    intel_combined = "\n\n".join(intel_parts)

    step_logs: list[dict] = []
    _s = _Step("interview_prep", step_logs, output_file="interview_prep.md")
    _s.prompt_text = load_skill("interview_prep").render(
        stages=stages_str,
        job_description=job_description,
        resume=resume,
        role_intel=strategy,
        positioning_brief=positioning_brief_text or "(not provided)",
        intel_section=f"\n=== ADDITIONAL INTEL ===\n{intel_combined}\n" if intel_combined else "",
    )
    try:
        with _s, console.status("[cyan]Generating interview prep...[/cyan]", spinner="dots"):
            for chunk in llm.interview_prep(
                job_description, resume, strategy, model,
                positioning_brief=positioning_brief_text,
                intel=intel_combined,
                stages=stages_str,
                provider=provider,
            ):
                _s.collect(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    prep_text = _clean_llm_output(_s.output)
    if not prep_text:
        console.print("[yellow]Prep came back empty.[/yellow]")
        sys.exit(1)

    out_path = folder / "interview_prep.md"
    out_path.write_text(
        f"# Interview Prep — {job.title} @ {job.company}\n\n{prep_text}\n",
        encoding="utf-8",
    )

    console.print()
    console.print(Panel(prep_text, title="[bold]Interview Prep[/bold]", style="green"))
    console.print(f"\n[green]Saved:[/green] {out_path}")

    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _in = len(_enc.encode(_s.prompt_text))
        _out = len(_enc.encode(_s.output))
        console.print(f"[dim]Tokens: {_in:,} in + {_out:,} out  [{_s.duration}s][/dim]")
    except Exception:
        pass


# ---------- questions ----------


@main.command()
@click.argument("job_id")
@click.option(
    "--stage", "stage_arg", default="",
    help=f"Focus on one stage: {', '.join(_PREP_STAGES)}. Default: all stages (one section per stage).",
)
@click.option("--count", "-n", default=5, show_default=True, help="Number of questions per stage.")
@click.option("--model", "model_arg", default="", help="Override model for this run.")
@click.option("--provider", "provider_arg", default="", help="Override provider.")
def questions(job_id: str, stage_arg: str, count: int, model_arg: str, provider_arg: str) -> None:
    """Generate targeted interview questions with STAR answer frameworks.

    Appends to questions.md in the package folder. Each run adds a new
    dated section — previous questions are never overwritten.
    """
    cfg = _require_config()
    model = model_arg or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = provider_arg or cfg.get("provider", "ollama")

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

    # Resolve which stages to generate.
    if stage_arg:
        key = stage_arg.lower().strip()
        if key not in _PREP_STAGE_LABELS:
            console.print(f"[red]Unknown stage '{stage_arg}'.[/red] Valid: {', '.join(_PREP_STAGES)}")
            sys.exit(1)
        stages_to_run = [(key, _PREP_STAGE_LABELS[key])]
    else:
        stages_to_run = list(_PREP_STAGE_LABELS.items())

    console.print(
        Panel.fit(
            f"[bold]Interview Questions[/bold] [cyan]{job.company}[/cyan] — {job.title}  [dim]({job_id})[/dim]\n"
            f"[dim]{count} questions × {len(stages_to_run)} stage(s)[/dim]",
            style="cyan",
        )
    )

    def _read(fname: str) -> str:
        p = folder / fname
        return p.read_text(encoding="utf-8") if p.exists() else ""

    resume = _read("resume.md")
    strategy = _read("strategy.md")
    positioning_brief_text = _read("positioning_brief.md")
    job_description = _read("job_description.md") or strategy

    if not resume:
        console.print("[red]resume.md not found in package folder.[/red]")
        sys.exit(1)
    if not job_description:
        console.print("[red]No job description or strategy found in package folder.[/red]")
        sys.exit(1)

    # Read intel folder + Notion notes.
    _vision_model = cfg.get("intel_vision_model", "")
    _vision_provider = cfg.get("intel_vision_provider", provider) if _vision_model else ""
    intel_folder_text, intel_warnings = _read_intel_folder(
        folder, vision_model=_vision_model, vision_provider=_vision_provider,
    )
    for w in intel_warnings:
        console.print(f"[yellow]Intel warning:[/yellow] {w}")

    # Context summary.
    console.print("\n[dim]Context loaded:[/dim]")
    console.print(f"[dim]  {'resume.md':<28} ✓[/dim]")
    console.print(f"[dim]  {'job description':<28} ✓[/dim]")
    console.print(f"[dim]  {'role intel / strategy':<28} {'✓' if strategy else '—'}[/dim]")
    console.print(f"[dim]  {'positioning brief':<28} {'✓' if positioning_brief_text else '—'}[/dim]")

    intel_dir = folder / "intel"
    intel_files = [
        f for f in sorted(intel_dir.iterdir())
        if not f.is_dir()
    ] if intel_dir.exists() else []
    _processable_exts = {".pdf"} | _INTEL_TEXT_EXTS | (_INTEL_IMAGE_EXTS if _vision_model else set())
    loaded_files = [f for f in intel_files if f.suffix.lower() in _processable_exts]
    if _vision_model:
        console.print(f"[dim]  {'vision model':<28} {_vision_model} ({_vision_provider})[/dim]")
    if loaded_files:
        for f in loaded_files:
            label = "intel/" + f.name
            if f.suffix.lower() in _INTEL_IMAGE_EXTS:
                cache_path = intel_dir / ".cache" / f"{f.stem}.extracted.md"
                note = " (cached)" if cache_path.exists() and cache_path.stat().st_mtime >= f.stat().st_mtime else " (vision)"
            else:
                note = ""
            console.print(f"[dim]  {label:<28} ✓{note}[/dim]")
    else:
        console.print(f"[dim]  {'intel/ (empty)':<28} — tip: drop .pdf/.md/.txt files here[/dim]")

    notion_notes = store.load_job_notes(job_id)
    console.print(f"[dim]  {'Notion page notes':<28} {'✓' if notion_notes else '— (not connected or empty)'}[/dim]")
    console.print()

    intel_parts: list[str] = []
    if intel_folder_text:
        intel_parts.append(intel_folder_text)
    if notion_notes:
        intel_parts.append(f"--- Notion page notes ---\n{notion_notes}")
    intel_combined = "\n\n".join(intel_parts)

    # Load existing questions.md for deduplication context.
    questions_path = folder / "questions.md"
    existing_questions = ""
    if questions_path.exists():
        existing_questions = questions_path.read_text(encoding="utf-8").strip()

    # Generate questions for each stage and append.
    import datetime as _dt
    today = _dt.date.today().isoformat()
    all_new_sections: list[str] = []
    step_logs: list[dict] = []

    for _stage_key, _stage_label in stages_to_run:
        _s = _Step(f"questions_{_stage_key}", step_logs, output_file="questions.md")
        _s.prompt_text = load_skill("questions").render(
            count=count,
            stage=_stage_label,
            job_description=job_description,
            resume=resume,
            role_intel=strategy,
            positioning_brief=positioning_brief_text or "(not provided)",
            intel_section=f"\n=== ADDITIONAL INTEL ===\n{intel_combined}\n" if intel_combined else "",
            existing_questions=existing_questions or "(none yet)",
        )
        try:
            with _s, console.status(f"[cyan]Generating questions for {_stage_label}...[/cyan]", spinner="dots"):
                for chunk in llm.generate_questions(
                    job_description, resume, strategy, model,
                    positioning_brief=positioning_brief_text,
                    intel=intel_combined,
                    existing_questions=existing_questions,
                    stage=_stage_label,
                    count=count,
                    provider=provider,
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

        section_text = _clean_llm_output(_s.output)
        if not section_text:
            console.print(f"[yellow]No output for stage '{_stage_label}' — skipping.[/yellow]")
            continue

        section = f"## Questions — {_stage_label.title()} (generated {today})\n\n{section_text}"
        all_new_sections.append(section)
        # Accumulate so subsequent stages know all already-generated questions.
        existing_questions = (existing_questions + "\n\n" + section).strip()

    if not all_new_sections:
        console.print("[yellow]No questions were generated.[/yellow]")
        sys.exit(1)

    new_content = "\n\n---\n\n".join(all_new_sections)

    # Append to questions.md (never overwrite).
    if questions_path.exists():
        existing_file = questions_path.read_text(encoding="utf-8").rstrip()
        questions_path.write_text(
            existing_file + "\n\n---\n\n" + new_content + "\n",
            encoding="utf-8",
        )
        console.print(f"\n[green]Appended to:[/green] {questions_path}")
    else:
        questions_path.write_text(
            f"# Interview Questions — {job.title} @ {job.company}\n\n{new_content}\n",
            encoding="utf-8",
        )
        console.print(f"\n[green]Saved:[/green] {questions_path}")

    console.print(Panel(new_content, title="[bold]Interview Questions[/bold]", style="green"))

    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _total_in = sum(len(_enc.encode(s.get("prompt_text", ""))) for s in step_logs)
        _total_out = sum(len(_enc.encode(s.get("output_text", ""))) for s in step_logs)
        console.print(f"[dim]Tokens: {_total_in:,} in + {_total_out:,} out[/dim]")
    except Exception:
        pass


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
    _s.prompt_text = load_skill("critique").render(
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


# ---------- answer ----------


@main.command()
@click.argument("job_id")
@click.option("--model", "model_arg", default="", help="Override model for this run.")
@click.option("--provider", "provider_arg", default="", help="Override provider.")
def answer(job_id: str, model_arg: str, provider_arg: str) -> None:
    """Draft answers to application form questions for a job."""
    from . import pipeline as _pipeline

    cfg = _require_config()
    model = model_arg or cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    provider = provider_arg or cfg.get("provider", "ollama")

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
            f"[bold]Answer Questions[/bold] [cyan]{job.company}[/cyan] — {job.title}  [dim]({job_id})[/dim]",
            style="cyan",
        )
    )

    try:
        ctx = _pipeline.PipelineContext.from_config(model=model, provider=provider)
    except storage.StorageError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    questions = _read_multiline("Paste form questions (end with ---):")
    if not questions.strip():
        console.print("[yellow]No questions provided — nothing to answer.[/yellow]")
        sys.exit(0)

    step_logs: list[dict] = []
    current_answer = ""

    while True:
        _s = _Step("answer_questions", step_logs, output_file="answers.md")
        try:
            with _s, console.status("[cyan]Drafting answers...[/cyan]", spinner="dots"):
                for chunk in llm.answer_questions(
                    resume=ctx.resume,
                    stories=ctx.stories,
                    role_intel=(folder / "strategy.md").read_text(encoding="utf-8") if (folder / "strategy.md").exists() else "",
                    company_context="",
                    positioning_brief=(folder / "positioning_brief.md").read_text(encoding="utf-8") if (folder / "positioning_brief.md").exists() else "",
                    applicant_profile=_pipeline._applicant_profile_block(ctx.applicant_profile) if ctx.applicant_profile else "",
                    questions=questions,
                    model=model,
                    provider=provider,
                ):
                    _s.collect(chunk)
        except llm.LLMError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

        current_answer = _clean_llm_output(_s.output)
        if not current_answer:
            console.print("[yellow]No answer generated.[/yellow]")
            sys.exit(1)

        console.print()
        console.print(Panel(current_answer, title="[bold]Drafted Answers[/bold]", style="green"))

        choice = _pick("What next?", ["accept", "edit", "refine", "quit"], default="accept")

        if choice == "accept":
            break
        elif choice == "edit":
            edited = click.edit(current_answer, extension=".md")
            if edited is not None:
                current_answer = edited.strip()
            break
        elif choice == "refine":
            feedback = Prompt.ask("Feedback (describe what to change)")
            if feedback.strip():
                questions = questions + f"\n\nFeedback: {feedback}"
        elif choice == "quit":
            console.print("[dim]Discarded — nothing saved.[/dim]")
            return

    # Append to answers.md with timestamp header (never overwrite prior runs).
    timestamp = _utcnow().strftime("%Y-%m-%d %H:%M")
    section = f"## Answers — {timestamp}\n\n{current_answer}"
    answers_path = folder / "answers.md"
    if answers_path.exists():
        existing = answers_path.read_text(encoding="utf-8").rstrip()
        answers_path.write_text(existing + "\n\n---\n\n" + section + "\n", encoding="utf-8")
        console.print(f"\n[green]Appended to:[/green] {answers_path}")
    else:
        answers_path.write_text(
            f"# Application Answers — {job.title} @ {job.company}\n\n{section}\n",
            encoding="utf-8",
        )
        console.print(f"\n[green]Saved:[/green] {answers_path}")

    try:
        import tiktoken as _tiktoken
        _enc = _tiktoken.get_encoding("cl100k_base")
        _total_in = sum(len(_enc.encode(s.get("prompt_text", ""))) for s in step_logs)
        _total_out = sum(len(_enc.encode(s.get("output_text", ""))) for s in step_logs)
        console.print(f"[dim]Tokens: {_total_in:,} in + {_total_out:,} out[/dim]")
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


# ---------- process-queue ----------

@main.command("process-queue", hidden=True)
@click.option("--queue-id", "queue_id", default="default", help="Worker identifier for queue claims.")
def process_queue(queue_id: str) -> None:
    """Process one job from the queue (non-interactive, auto-resolves all gates)."""
    from . import pipeline as _pipeline
    from .queue import MemoryQueue, QueueError

    # We use MemoryQueue by default; a future SQLiteQueue can be swapped in here.
    # For now, the queue instance must be provided externally (e.g., by a daemon).
    # This command is designed to be called programmatically by OpenClaw or a worker script.
    console.print("[yellow]process-queue requires an active QueueStore instance.[/yellow]")
    console.print("[dim]This command is designed for programmatic use by OpenClaw or a worker.")
    console.print("Example usage from Python:")
    console.print("  from applycling.queue import MemoryQueue")
    console.print("  q = MemoryQueue()")
    console.print("  q.enqueue('https://...')")
    console.print("  # then: applycling process-queue[/dim]")
    console.print()

    cfg = _require_config()
    model = cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup first.")
        sys.exit(1)
    provider = cfg.get("provider", "ollama")

    # Try to load a shared queue instance from the module-level registry.
    # If no shared queue is registered, create a transient MemoryQueue (no-op).
    import applycling.queue as _queue_module
    queue_store = getattr(_queue_module, "_shared_queue", None)
    if queue_store is None:
        console.print("[red]No shared queue registered. Set applycling.queue._shared_queue to a QueueStore instance.[/red]")
        sys.exit(1)

    queued_job = queue_store.dequeue(claimer_id=queue_id)
    if queued_job is None:
        console.print("[dim]Queue is empty — nothing to process.[/dim]")
        return

    console.print(f"[cyan]Processing queue job:[/cyan] {queued_job.id} ({queued_job.url})")

    try:
        ctx = _pipeline.PipelineContext.from_config(
            model=model,
            provider=provider,
        )

        # Fetch job posting from URL.
        from . import scraper
        with console.status("[cyan]Fetching job posting...[/cyan]", spinner="dots"):
            posting, _ = scraper.fetch_job_posting(queued_job.url, model, provider=provider)

        title = posting.title
        company = posting.company
        job_description = posting.description
        company_url = posting.company_url

        console.print(f"[green]Fetched:[/green] [bold]{title}[/bold] @ [bold]{company}[/bold]")

        with console.status("[cyan]Running pipeline (non-interactive)...[/cyan]", spinner="dots"):
            result = _pipeline.run_add(
                job_url=queued_job.url,
                job_title=title,
                job_company=company,
                job_description=job_description,
                context=ctx,
                company_url=company_url or None,
                on_gate=None,  # AutoResolver: no gate = auto-proceed
                want_summary=True,
                render_pdf=True,
            )

        output_root = Path(cfg["output_dir"]).expanduser() if cfg.get("output_dir") else None
        with console.status("[cyan]Assembling package...[/cyan]", spinner="dots"):
            folder = _pipeline.persist_add_result(
                result,
                output_root=output_root,
                generate_docx=cfg.get("generate_docx", False),
                generate_run_log=cfg.get("generate_run_log", True),
            )

        # Update tracker with package folder.
        store = get_store()
        try:
            store.update_job(result.job.id, package_folder=str(folder))
        except TrackerError:
            pass  # Non-fatal; folder still written.

        queue_store.mark_completed(queued_job.id)
        console.print(f"[green]Done:[/green] {folder}")

    except Exception as e:
        queue_store.mark_failed(queued_job.id, str(e))
        console.print(f"[red]Failed:[/red] {e}")
        sys.exit(1)


# ---------- telegram ----------


@main.group()
def telegram() -> None:
    """Telegram integration: setup and submit jobs from your phone."""


@telegram.command("setup")
def telegram_setup() -> None:
    """Configure your Telegram bot token and chat ID."""
    console.print("[bold]Telegram setup[/bold]")
    console.print(
        "\n[dim]You need a Telegram bot token and your chat ID.\n"
        "Create a bot via @BotFather and get its token.\n"
        "Send a message to the bot, then visit:\n"
        "  https://api.telegram.org/bot<TOKEN>/getUpdates\n"
        "to find your chat_id.[/dim]\n"
    )
    token = Prompt.ask("Bot token (from @BotFather)")
    chat_id = Prompt.ask("Your chat ID")
    storage.save_telegram_config(token.strip(), chat_id.strip())
    console.print("[green]Telegram config saved.[/green]")

    # Quick connectivity test
    from .telegram_notify import TelegramNotifier, TelegramError
    try:
        notifier = TelegramNotifier(token.strip(), chat_id.strip())
        notifier.notify("✅ applycling connected! Send me a job URL to get started.")
        console.print("[green]Test message sent — check Telegram.[/green]")
    except TelegramError as e:
        console.print(f"[yellow]Config saved but test message failed:[/yellow] {e}")


@telegram.command("add")
@click.argument("url")
@click.option("--model", "model_arg", default="", help="Override model from config.")
@click.option("--provider", "provider_arg", default="", help="Override provider from config.")
def telegram_add(url: str, model_arg: str, provider_arg: str) -> None:
    """Queue a job URL for background processing with Telegram status updates."""
    try:
        tg_cfg = storage.load_telegram_config()
    except storage.StorageError:
        console.print("[red]Telegram not configured.[/red] Run: applycling telegram setup")
        sys.exit(1)

    cfg = _require_config()
    _require_resume()

    # Build args for the background worker
    import subprocess
    worker_cmd = [sys.executable, "-m", "applycling.cli", "telegram", "_run", url]
    if model_arg:
        worker_cmd += ["--model", model_arg]
    if provider_arg:
        worker_cmd += ["--provider", provider_arg]

    import os
    log_dir = Path(cfg.get("output_dir", "./output")).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "telegram_worker.log"

    with open(log_path, "a") as log_file:
        subprocess.Popen(
            worker_cmd,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    console.print(f"[green]Queued.[/green] Processing in background — check Telegram for updates.")
    console.print(f"[dim]Worker log: {log_path}[/dim]")


@telegram.command("_run", hidden=True)
@click.argument("url")
@click.option("--model", "model_arg", default="", help="Override model from config.")
@click.option("--provider", "provider_arg", default="", help="Override provider from config.")
def telegram_run(url: str, model_arg: str, provider_arg: str) -> None:
    """Internal: run the full pipeline and deliver results via Telegram."""
    from . import pipeline as _pipeline
    from .telegram_notify import TelegramNotifier

    try:
        tg_cfg = storage.load_telegram_config()
    except storage.StorageError as e:
        sys.exit(f"Config error: {e}")

    notifier = TelegramNotifier(tg_cfg["bot_token"], tg_cfg["chat_id"])
    try:
        _pipeline.run_add_notify(
            url,
            notifier,
            model=model_arg or None,
            provider=provider_arg or None,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()  # captured by worker log
        try:
            notifier.notify(f"❌ Worker crashed.\nError: {e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
