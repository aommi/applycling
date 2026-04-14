#!/usr/bin/env python3
"""Quick prompt tester — runs one step or the full pipeline end-to-end.

Usage:
    # Preview raw PDF extraction (no LLM, no save)
    python test_prompt.py import --pdf ~/Downloads/resume.pdf

    # Single step
    python test_prompt.py tailor --jd /tmp/jd.txt
    python test_prompt.py cover_letter --jd /tmp/jd.txt --strategy /tmp/strategy.txt

    # Full pipeline (all steps in sequence, outputs written to /tmp/test_run/)
    python test_prompt.py pipeline --jd /tmp/jd.txt
    python test_prompt.py pipeline --jd /tmp/jd.txt --review   # pause after each step

Reads data/resume.md and data/config.json automatically.
Override model/provider with --model and --provider flags.

Steps: import, tailor, cover_letter, role_intel, profile_summary, fit_summary, pipeline
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from applycling import llm, storage, prompts


def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        sys.exit(f"File not found: {path}")
    return p.read_text(encoding="utf-8").strip()


def _collect(iterator) -> str:
    parts = []
    for chunk in iterator:
        print(chunk, end="", flush=True)
        parts.append(chunk)
    print()
    return "".join(parts)


def _clean(text: str) -> str:
    """Strip code fences and leading/trailing whitespace."""
    import re
    text = re.sub(r"^```[a-z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _header(title: str):
    print(f"\n{'━'*60}")
    print(f"  {title}")
    print(f"{'━'*60}\n")


def _gate(step_name: str, out_file: Path, review: bool) -> bool:
    """If review mode, pause and ask to continue. Returns False if user aborts."""
    if not review:
        return True
    print(f"\n[saved: {out_file}]")
    print(f"\n  Continue?  [enter] next step   [s] skip next   [q] quit  ", end="")
    try:
        ans = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "q"
    if ans == "q":
        print("Aborted.")
        return False
    return True  # 's' is handled per-step by the caller checking skip


def run_pipeline(jd: str, resume: str, model: str, provider: str,
                 profile: dict, stories, linkedin_profile, out_dir: Path,
                 review: bool = False):
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = []

    def _save(name: str, text: str) -> Path:
        p = out_dir / name
        p.write_text(text)
        return p

    def _gate_or_skip(step_name: str, out_file: Path) -> bool:
        """Returns False if user chose quit."""
        if not review:
            print(f"[saved: {out_file}]")
            return True
        print(f"\n[saved: {out_file}]")
        print("  [enter] next   [q] quit  ", end="")
        try:
            ans = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "q"
        return ans != "q"

    # Step 1: Role Intel
    _header("STEP 1 — Role Intel")
    strategy = ""
    try:
        strategy_raw = _collect(llm.role_intel(jd, model, resume=resume, provider=provider))
        strategy = _clean(strategy_raw)
        p = _save("strategy.md", strategy)
        if not _gate_or_skip("role_intel", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("role_intel", str(e)))

    # Step 2: Resume Tailor
    _header("STEP 2 — Resume Tailor")
    tailored = resume
    try:
        tailor_raw = _collect(llm.tailor_resume(
            resume, jd, model,
            stories=stories, strategy=strategy or None,
            voice_tone=profile.get("voice_tone"),
            never_fabricate=profile.get("never_fabricate"),
            linkedin_profile=linkedin_profile,
            provider=provider,
        ))
        tailored = _clean(tailor_raw)
        p = _save("resume_tailored.md", tailored)
        if not _gate_or_skip("resume_tailor", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("resume_tailor", str(e)))

    # Step 3: Format Resume
    _header("STEP 3 — Format Resume")
    formatted = tailored
    try:
        fmt_raw = _collect(llm.format_resume(tailored, model, provider=provider))
        formatted = _clean(fmt_raw)
        p = _save("resume_formatted.md", formatted)
        if not _gate_or_skip("format_resume", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("format_resume", str(e)))

    # Step 4: Profile Summary
    _header("STEP 4 — Profile Summary")
    try:
        summary_raw = _collect(llm.get_profile_summary(resume, jd, model, provider=provider))
        summary = _clean(summary_raw)
        p = _save("profile_summary.md", summary)
        if not _gate_or_skip("profile_summary", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("profile_summary", str(e)))

    # Step 5: Positioning Brief
    _header("STEP 5 — Positioning Brief")
    try:
        brief_raw = _collect(llm.positioning_brief(strategy, formatted, jd, model, provider=provider))
        brief = _clean(brief_raw)
        p = _save("positioning_brief.md", brief)
        if not _gate_or_skip("positioning_brief", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("positioning_brief", str(e)))

    # Step 6: Cover Letter
    _header("STEP 6 — Cover Letter")
    try:
        cl_raw = _collect(llm.cover_letter(
            strategy, formatted, jd, model,
            voice_tone=profile.get("voice_tone"), provider=provider,
        ))
        cl = _clean(cl_raw)
        p = _save("cover_letter.md", cl)
        if not _gate_or_skip("cover_letter", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("cover_letter", str(e)))

    # Step 7: Fit Summary
    _header("STEP 7 — Fit Summary")
    try:
        fit_raw = _collect(llm.get_fit_summary(resume, jd, model, provider=provider))
        fit = _clean(fit_raw)
        p = _save("fit_summary.md", fit)
        if not _gate_or_skip("fit_summary", p):
            return
    except llm.LLMError as e:
        print(f"[FAILED] {e}")
        errors.append(("fit_summary", str(e)))

    # Summary
    print(f"\n{'━'*60}")
    if errors:
        print(f"  Pipeline complete with {len(errors)} error(s):")
        for step, msg in errors:
            print(f"  ✗ {step}: {msg}")
    else:
        print(f"  Pipeline complete — all steps OK")
        print(f"  Output: {out_dir}/")
    print(f"{'━'*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["import", "tailor", "cover_letter", "role_intel",
                                          "profile_summary", "fit_summary", "pipeline"])
    parser.add_argument("--jd", default="", help="Path to job description text file (required for all steps except import)")
    parser.add_argument("--strategy", default="")
    parser.add_argument("--resume", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--out", default="/tmp/test_run", help="Output dir for pipeline mode")
    parser.add_argument("--review", action="store_true", help="Pause after each step for confirmation")
    parser.add_argument("--pdf", default="", help="PDF path for the import step")
    args = parser.parse_args()

    cfg = storage.load_config()
    model = args.model or cfg.get("model")
    provider = args.provider or cfg.get("provider", "ollama")
    resume = _read(args.resume) if args.resume else storage.load_resume()
    jd = _read(args.jd) if args.jd else ""
    strategy = _read(args.strategy) if args.strategy else ""
    profile = storage.load_profile() or {}
    stories = storage.load_stories()
    linkedin_profile = storage.load_linkedin_profile() if cfg.get("use_linkedin_profile", True) else None

    print(f"\nmodel={model}  provider={provider}\n")

    if args.step == "import":
        if not args.pdf:
            sys.exit("--pdf is required for the import step")
        from applycling import pdf_import
        pdf_path = Path(args.pdf).expanduser()
        _header("IMPORT — Raw PDF extraction (no LLM, no save)")
        try:
            raw = pdf_import.extract_text(pdf_path)
        except pdf_import.PDFImportError as e:
            sys.exit(f"[FAILED] {e}")
        out_file = Path("/tmp/resume_preview.md")
        out_file.write_text(raw)
        print(raw)
        print(f"\n{'━'*60}")
        print(f"  {len(raw)} chars extracted from {pdf_path.name}")
        print(f"  Saved for review: {out_file}")
        print(f"  To save as your base resume: applycling setup → replace → pdf")
        print(f"{'━'*60}\n")
        import subprocess
        subprocess.run(["open", "-R", str(out_file)])
        return

    if args.step == "pipeline":
        run_pipeline(jd, resume, model, provider, profile, stories,
                     linkedin_profile, Path(args.out), review=args.review)
        return

    _header(args.step.upper())

    if args.step == "tailor":
        _collect(llm.tailor_resume(resume, jd, model, stories=stories,
            strategy=strategy or None, voice_tone=profile.get("voice_tone"),
            never_fabricate=profile.get("never_fabricate"),
            linkedin_profile=linkedin_profile, provider=provider))
    elif args.step == "role_intel":
        _collect(llm.role_intel(jd, model, resume=resume, provider=provider))
    elif args.step == "cover_letter":
        _collect(llm.cover_letter(strategy, resume, jd, model,
            voice_tone=profile.get("voice_tone"), provider=provider))
    elif args.step == "profile_summary":
        _collect(llm.get_profile_summary(resume, jd, model, provider=provider))
    elif args.step == "fit_summary":
        _collect(llm.get_fit_summary(resume, jd, model, provider=provider))


if __name__ == "__main__":
    main()
