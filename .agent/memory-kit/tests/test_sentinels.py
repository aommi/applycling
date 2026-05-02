"""Tests for sentinel preservation and --check drift detection."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.utils import (
    write_managed_section,
    check_managed_section,
    check_fully_generated,
    GENERATED_BANNER_MD,
    GENERATED_BANNER_SH,
    SENTINEL_START,
    SENTINEL_END,
)


# ── write_managed_section ────────────────────────────────────────────────────


def test_write_creates_file_with_banner():
    """First create: header + sentinel block with banner."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        result = write_managed_section(path, "# Header", "managed content", "TEST.md")
        assert "created" in result
        content = path.read_text()
        assert "# Header" in content
        assert SENTINEL_START in content
        assert GENERATED_BANNER_MD in content
        assert "managed content" in content
        assert SENTINEL_END in content


def test_write_replaces_block_when_sentinels_present():
    """Re-run with sentinels: replaces only the managed block, preserves outer content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# Header", "version 1", "TEST.md")

        # Add custom content outside sentinels
        existing = path.read_text()
        custom = "\n## Custom Section\n\nMy notes here.\n"
        path.write_text(existing + custom)

        # Re-generate with new content
        result = write_managed_section(path, "# Header", "version 2", "TEST.md")
        assert "updated" in result
        content = path.read_text()
        assert "version 2" in content
        assert "version 1" not in content
        assert "My notes here." in content  # preserved


def test_write_appends_when_no_sentinels():
    """Existing file without sentinels: appends managed block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        path.write_text("# Existing content\n\nCustom stuff.\n")
        result = write_managed_section(path, "# Header", "managed", "TEST.md")
        assert "appended" in result
        content = path.read_text()
        assert "Custom stuff." in content  # preserved
        assert "managed" in content  # appended


def test_write_unchanged_when_block_matches():
    """Re-run with same content: no changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# Header", "content", "TEST.md")
        result = write_managed_section(path, "# Header", "content", "TEST.md")
        assert "unchanged" in result


def test_write_with_frontmatter():
    """First create with YAML frontmatter: frontmatter before header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.mdc"
        frontmatter = "---\ndescription: Test\nalwaysApply: true\n---\n"
        result = write_managed_section(
            path, "# Memory", "managed content", "TEST.mdc", frontmatter=frontmatter
        )
        assert "created" in result
        content = path.read_text()
        assert content.startswith("---\n")
        assert "alwaysApply" in content
        assert "# Memory" in content


# ── check_managed_section ────────────────────────────────────────────────────


def test_check_managed_returns_none_when_matching():
    """Matching block: no drift."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# H", "content", "TEST.md")
        result = check_managed_section(path, "content", "TEST.md")
        assert result is None


def test_check_managed_detects_drift():
    """Different content: returns a diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# H", "original", "TEST.md")
        result = check_managed_section(path, "changed", "TEST.md")
        assert result is not None
        assert "original" in result or "changed" in result


def test_check_managed_ignores_outer_content():
    """Only the managed block is compared; outer custom content doesn't cause drift."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# H", "content", "TEST.md")
        # Add custom content outside sentinels
        existing = path.read_text()
        path.write_text(existing + "\n## Custom\n\nMy notes.\n")
        # Should still be clean — only the managed block matters
        result = check_managed_section(path, "content", "TEST.md")
        assert result is None


def test_check_managed_reports_missing_sentinels():
    """No sentinels at all: reports as needing generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        path.write_text("# Just some content")
        result = check_managed_section(path, "anything", "TEST.md")
        assert result is not None
        assert "no managed block" in result


def test_check_managed_returns_drift_when_file_missing():
    """File doesn't exist: reports as drift (not yet generated)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nonexistent.md"
        result = check_managed_section(path, "content", "nonexistent.md")
        assert result is not None
        assert "does not exist" in result


# ── check_fully_generated ────────────────────────────────────────────────────


def test_check_fully_generated_returns_none_when_matching():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        path.write_text("exact content")
        result = check_fully_generated(path, "exact content", "TEST.md")
        assert result is None


def test_check_fully_generated_detects_drift():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        path.write_text("old content")
        result = check_fully_generated(path, "new content", "TEST.md")
        assert result is not None


def test_check_fully_generated_returns_drift_when_file_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nonexistent.md"
        result = check_fully_generated(path, "content", "nonexistent.md")
        assert result is not None
        assert "does not exist" in result


# ── Banner presence ──────────────────────────────────────────────────────────


def test_banner_in_md_managed_block():
    """Generated banner appears inside the sentinel block (not outside it)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "TEST.md"
        write_managed_section(path, "# H", "content", "TEST.md")
        content = path.read_text()
        start = content.index(SENTINEL_START)
        end = content.index(SENTINEL_END) + len(SENTINEL_END)
        block = content[start:end]
        assert GENERATED_BANNER_MD in block
        # Banner should NOT be outside the block
        before_block = content[:start]
        after_block = content[end:]
        assert GENERATED_BANNER_MD not in before_block
        assert GENERATED_BANNER_MD not in after_block
