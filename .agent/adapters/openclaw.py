"""
Openclaw Adapter — thin wrapper around memory-kit adapter.

Loads project config from .agent/project.yaml and delegates to the reusable
memory-kit adapter in .agent/memory-kit/adapters/.
"""
import importlib.util
from pathlib import Path
import yaml


def _load_mk_adapter():
    mk_dir = Path(__file__).parent.parent / "memory-kit"
    spec = importlib.util.spec_from_file_location(
        "mk_openclaw",
        mk_dir / "adapters" / "openclaw.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate


_generate = _load_mk_adapter()


def generate(project_root: Path):
    """Generate Openclaw configuration."""
    config_path = project_root / ".agent" / "project.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return _generate(project_root, config)
