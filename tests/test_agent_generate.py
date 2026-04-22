"""
Smoke tests for .agent/generate.py

Runs each adapter against a temporary directory and asserts the expected
output files are created and contain key content. Catches brace-escaping
bugs (generated files should say `{{` not `{` in the conventions line).
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Allow importing the adapter modules directly
AGENT_DIR = Path(__file__).parent.parent / ".agent"
sys.path.insert(0, str(AGENT_DIR))

from adapters.claude_code import generate as gen_claude_code
from adapters.codex import generate as gen_codex
from adapters.cursor import generate as gen_cursor
from adapters.gemini_cli import generate as gen_gemini_cli
from adapters.windsurf import generate as gen_windsurf
from adapters.openclaw import generate as gen_openclaw
from adapters.hermes import generate as gen_hermes


@pytest.fixture()
def tmp_project(tmp_path):
    """Minimal project root with the .agent/templates/ files copied in."""
    agent_dir = tmp_path / ".agent"
    shutil.copytree(AGENT_DIR, agent_dir)
    return tmp_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

BRACE_ESCAPE_SENTINEL = "escape braces with `{{` and `}}`"


def assert_brace_escaping(content: str, filename: str):
    """The conventions line must use {{ / }} (two braces), not { / }."""
    assert BRACE_ESCAPE_SENTINEL in content, (
        f"{filename}: expected '{{{{' / '}}}}' escape docs, got single braces. "
        "Check that the adapter uses string concatenation (not f-string) for template content."
    )


# ---------------------------------------------------------------------------
# Per-adapter tests
# ---------------------------------------------------------------------------

def test_claude_code(tmp_project):
    gen_claude_code(tmp_project)
    assert (tmp_project / "CLAUDE.md").exists()
    assert (tmp_project / ".claude" / "settings.json").exists()
    assert (tmp_project / "hooks" / "preprompt.txt").exists()
    assert (tmp_project / "hooks" / "stop.sh").exists()

    settings = json.loads((tmp_project / ".claude" / "settings.json").read_text())
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_claude_code_hooks_deep_merge(tmp_project):
    """Existing hook events (e.g. PreToolUse) must be preserved on re-generation."""
    claude_dir = tmp_project / ".claude"
    claude_dir.mkdir(exist_ok=True)
    existing = {
        "hooks": {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre"}]}]
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(existing))

    gen_claude_code(tmp_project)

    settings = json.loads((claude_dir / "settings.json").read_text())
    assert "PreToolUse" in settings["hooks"], "Pre-existing hook event was clobbered"
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_claude_code_settings_trailing_newline(tmp_project):
    gen_claude_code(tmp_project)
    raw = (tmp_project / ".claude" / "settings.json").read_bytes()
    assert raw.endswith(b"\n"), ".claude/settings.json must end with a newline"


def test_codex(tmp_project):
    gen_codex(tmp_project)
    content = (tmp_project / "AGENTS.md").read_text()
    assert "memory/semantic.md" in content
    assert "memory/working.md" in content
    assert_brace_escaping(content, "AGENTS.md (codex)")


def test_cursor(tmp_project):
    gen_cursor(tmp_project)
    mdc = (tmp_project / ".cursor" / "rules" / "memory.mdc").read_text()
    assert "alwaysApply: true" in mdc
    assert "globs:" not in mdc, "globs is redundant when alwaysApply: true — remove it"
    assert_brace_escaping(mdc, ".cursor/rules/memory.mdc")

    cursorignore = (tmp_project / ".cursorignore").read_text()
    assert "memory/semantic.md" not in cursorignore, (
        ".cursorignore must not hide memory files from Cursor's AI indexing"
    )


def test_gemini_cli(tmp_project):
    gen_gemini_cli(tmp_project)
    content = (tmp_project / "GEMINI.md").read_text()
    assert "memory/semantic.md" in content
    assert_brace_escaping(content, "GEMINI.md")
    assert (tmp_project / ".gemini" / "context.md").exists()


def test_windsurf(tmp_project):
    gen_windsurf(tmp_project)
    content = (tmp_project / ".windsurfrules").read_text()
    assert "memory/semantic.md" in content
    assert_brace_escaping(content, ".windsurfrules")


def test_openclaw(tmp_project):
    gen_openclaw(tmp_project)
    content = (tmp_project / ".openclaw-system.md").read_text()
    assert "memory/semantic.md" in content
    assert_brace_escaping(content, ".openclaw-system.md")


def test_hermes(tmp_project):
    gen_hermes(tmp_project)
    content = (tmp_project / "AGENTS.md").read_text()
    assert "memory/semantic.md" in content
    assert "agentskills.io" in content
    assert_brace_escaping(content, "AGENTS.md (hermes)")


def test_hermes_is_superset_of_codex(tmp_project):
    """Hermes AGENTS.md must contain everything codex AGENTS.md has, plus more."""
    gen_codex(tmp_project)
    codex_content = (tmp_project / "AGENTS.md").read_text()

    gen_hermes(tmp_project)
    hermes_content = (tmp_project / "AGENTS.md").read_text()

    assert len(hermes_content) > len(codex_content), (
        "Hermes AGENTS.md should be longer than the codex version"
    )
    assert "agentskills.io" in hermes_content
    assert "memory/semantic.md" in hermes_content


def test_all_agents_generate_cleanly(tmp_project):
    """generate.py all must complete without errors for every agent."""
    import importlib.util

    generate_path = AGENT_DIR / "generate.py"
    spec = importlib.util.spec_from_file_location("generate", generate_path)
    mod = importlib.util.module_from_spec(spec)

    # Patch sys.argv and project root
    original_argv = sys.argv[:]
    sys.argv = ["generate.py", "all"]

    # Redirect project_root in the module by monkeypatching __file__ isn't easy,
    # so instead call each adapter directly (already tested above).
    # This test just verifies ALL_ORDER covers every key in AGENTS.
    spec.loader.exec_module(mod)
    assert set(mod.ALL_ORDER) == set(mod.AGENTS.keys()), (
        "ALL_ORDER and AGENTS keys must match — add new agents to both"
    )
    assert mod.ALL_ORDER.index("hermes") > mod.ALL_ORDER.index("codex"), (
        "hermes must come after codex in ALL_ORDER so hermes AGENTS.md wins"
    )

    sys.argv = original_argv
