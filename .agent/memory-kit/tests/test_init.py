"""Tests for working memory bootstrap (init + _bootstrap_working_md)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate import _bootstrap_working_md


WORKING_EXAMPLE_SKELETON = (
    "# Working Memory\n\n"
    "## Current Focus\n\n"
    "(none)\n\n"
    "## In Progress\n\n"
    "(none)\n\n"
    "## Blocked\n\n"
    "(none)\n\n"
    "## Next Steps\n\n"
    "(none)\n"
)


# ── _bootstrap_working_md unit tests ──────────────────────────────────


def test_bootstrap_creates_working_md_from_example():
    """When example exists and working.md is missing, copy example to working.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        memory_dir = root / "memory"
        memory_dir.mkdir()

        # Write the example file
        (memory_dir / "working.example.md").write_text(WORKING_EXAMPLE_SKELETON)

        _bootstrap_working_md(root)

        working_path = memory_dir / "working.md"
        assert working_path.exists()
        assert working_path.read_text() == WORKING_EXAMPLE_SKELETON


def test_bootstrap_never_overwrites_existing_working_md():
    """When working.md already exists, leave it untouched."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        memory_dir = root / "memory"
        memory_dir.mkdir()

        existing_content = "# My existing working memory\n\nSome notes.\n"
        (memory_dir / "working.md").write_text(existing_content)

        _bootstrap_working_md(root)

        assert (memory_dir / "working.md").read_text() == existing_content


def test_bootstrap_falls_back_to_minimal_when_no_example():
    """When no example exists, create a minimal working.md skeleton."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        _bootstrap_working_md(root)

        working_path = root / "memory" / "working.md"
        assert working_path.exists()
        assert working_path.read_text() == "# Working Memory\n\n"


def test_bootstrap_creates_memory_dir_if_needed():
    """When memory/ dir doesn't exist, create it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        _bootstrap_working_md(root)

        assert (root / "memory").is_dir()
        assert (root / "memory" / "working.md").exists()


def test_bootstrap_idempotent():
    """Running bootstrap twice is safe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        memory_dir = root / "memory"
        memory_dir.mkdir()

        # No example — first run creates minimal
        _bootstrap_working_md(root)
        first_content = (memory_dir / "working.md").read_text()

        # Second run — file exists, should be untouched
        _bootstrap_working_md(root)
        assert (memory_dir / "working.md").read_text() == first_content


# ── init integration tests ────────────────────────────────────────────


def _run_init(project_root: Path, inputs: str) -> None:
    """Simulate cmd_init with automated stdin."""
    import io
    import generate

    real_stdin = sys.stdin
    real_argv = sys.argv
    try:
        sys.stdin = io.StringIO(inputs)
        sys.argv = ["generate.py", "init"]
        # Override project root detection
        generate.DEFAULT_PROJECT_ROOT = project_root
        generate.cmd_init(project_root)
    finally:
        sys.stdin = real_stdin
        sys.argv = real_argv


def test_init_creates_working_example_md():
    """cmd_init creates memory/working.example.md with the skeleton."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # name, description, arch, 8 agent answers, 3 capture answers = 14 lines
        _run_init(root, "testproj\nTest project.\n\n\n\n\n\n\n\n\n\n\n\n\n\n")

        example_path = root / "memory" / "working.example.md"
        assert example_path.exists()
        content = example_path.read_text()
        assert "## Current Focus" in content
        assert "(none)" in content


def test_init_gitignores_working_md():
    """cmd_init adds memory/working.md to .gitignore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _run_init(root, "testproj\nTest project.\n\n\n\n\n\n\n\n\n\n\n\n\n\n")

        gitignore = (root / ".gitignore").read_text()
        assert "memory/working.md" in gitignore.splitlines()


def test_init_materializes_working_md_from_example():
    """cmd_init creates memory/working.md matching the example."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _run_init(root, "testproj\nTest project.\n\n\n\n\n\n\n\n\n\n\n\n\n\n")

        working_path = root / "memory" / "working.md"
        example_path = root / "memory" / "working.example.md"
        assert working_path.exists()
        assert working_path.read_text() == example_path.read_text()
