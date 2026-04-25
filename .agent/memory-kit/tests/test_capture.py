"""Tests for configurable Claude Code memory capture levels."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.claude_code import _build_stop_sh, _normalize_capture_at
from adapters.utils import ensure_gitignored


def test_normalize_default_when_memory_missing():
    assert _normalize_capture_at({}) == ["response", "merge"]


def test_normalize_default_when_capture_at_null():
    assert _normalize_capture_at({"memory": {"capture_at": None}}) == ["response", "merge"]


def test_normalize_empty_list_is_valid_warning_mode():
    assert _normalize_capture_at({"memory": {"capture_at": []}}) == []


def test_normalize_bare_string_is_coerced():
    assert _normalize_capture_at({"memory": {"capture_at": "response"}}) == ["response"]


def test_normalize_unknown_level_is_skipped():
    assert _normalize_capture_at({"memory": {"capture_at": ["response", "unknown"]}}) == ["response"]


def test_normalize_non_string_level_is_skipped():
    assert _normalize_capture_at({"memory": {"capture_at": ["merge", 123]}}) == ["merge"]


def test_normalize_invalid_container_uses_default():
    assert _normalize_capture_at({"memory": {"capture_at": {"response": True}}}) == ["response", "merge"]


def test_normalize_deduplicates_preserving_order():
    assert _normalize_capture_at({"memory": {"capture_at": ["response", "merge", "response"]}}) == ["response", "merge"]


def test_normalize_all_valid_levels():
    assert _normalize_capture_at({"memory": {"capture_at": ["response", "commit", "merge"]}}) == ["response", "commit", "merge"]


def _check_bash_syntax(script: str) -> None:
    result = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"bash syntax error:\n{result.stderr}"


def test_build_empty_warns_and_has_valid_syntax():
    script = _build_stop_sh([])
    assert "Warning: memory.capture_at is empty" in script
    assert "Add response, commit, and/or merge" in script
    _check_bash_syntax(script)


def test_build_response_only_skips_sentinel_logic():
    script = _build_stop_sh(["response"])
    assert "git -C \"$REPO_ROOT\" diff HEAD --name-only" in script
    assert "emit_memory_reminder" in script
    assert "SENTINEL" not in script
    _check_bash_syntax(script)


def test_build_commit_only_uses_range_scan():
    script = _build_stop_sh(["commit"])
    assert "SENTINEL" in script
    assert "rev-list" in script
    assert "HAS_COMMIT" in script
    assert "Merge commit detected" not in script
    _check_bash_syntax(script)


def test_build_merge_only_detects_merge_commits():
    script = _build_stop_sh(["merge"])
    assert "SENTINEL" in script
    assert "HAS_MERGE" in script
    assert "Merge commit detected" in script
    _check_bash_syntax(script)


def test_build_commit_and_merge_can_fire_both_levels():
    script = _build_stop_sh(["commit", "merge"])
    assert "HAS_COMMIT" in script
    assert "HAS_MERGE" in script
    assert "Merge commit detected" in script
    _check_bash_syntax(script)


def test_build_all_levels_includes_response_and_range_logic():
    script = _build_stop_sh(["response", "commit", "merge"])
    assert "diff HEAD --name-only" in script
    assert "rev-list" in script
    assert "SENTINEL" in script
    _check_bash_syntax(script)


def test_build_header_reflects_enabled_levels():
    script = _build_stop_sh(["response", "merge"])
    assert "capture levels: response, merge" in script


def test_build_uses_revlist_parents_not_grep():
    # grep -c exits 1 on zero matches; rev-list --parents | wc -w is safe under set -e
    script = _build_stop_sh(["commit", "merge"])
    assert "grep -c" not in script
    assert "rev-list --parents" in script
    assert "wc -w" in script


# --- ensure_gitignored ---


def test_gitignore_creates_file_when_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        ensure_gitignored(root, ".agent/.last_checked_commit")
        content = (root / ".gitignore").read_text()
        assert content == ".agent/.last_checked_commit\n"


def test_gitignore_appends_to_existing_file_with_trailing_newline():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".gitignore").write_text("*.pyc\n")
        ensure_gitignored(root, ".agent/.last_checked_commit")
        content = (root / ".gitignore").read_text()
        assert content == "*.pyc\n.agent/.last_checked_commit\n"


def test_gitignore_appends_to_file_without_trailing_newline():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".gitignore").write_text("*.pyc")
        ensure_gitignored(root, ".agent/.last_checked_commit")
        content = (root / ".gitignore").read_text()
        assert content == "*.pyc\n.agent/.last_checked_commit\n"


def test_gitignore_skips_when_entry_already_present():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        original = "*.pyc\n.agent/.last_checked_commit\n"
        (root / ".gitignore").write_text(original)
        ensure_gitignored(root, ".agent/.last_checked_commit")
        assert (root / ".gitignore").read_text() == original


def test_gitignore_no_spurious_blank_lines():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".gitignore").write_text("*.pyc\n")
        ensure_gitignored(root, ".agent/.last_checked_commit")
        content = (root / ".gitignore").read_text()
        assert "\n\n" not in content  # no blank lines inserted


def test_normalize_memory_key_is_null():
    # YAML `memory:` with no children → config["memory"] is None → must not crash
    assert _normalize_capture_at({"memory": None}) == ["response", "merge"]
