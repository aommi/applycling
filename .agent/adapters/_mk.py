"""
Memory-kit dispatcher — loads parameterized adapters from .agent/memory-kit/
with unique module names to avoid collisions with the wrapper modules.
"""
import importlib.util
import sys
from pathlib import Path

_MK_DIR = Path(__file__).parent.parent / "memory-kit"


def load_adapter(name: str):
    """Load a memory-kit adapter by module name and return its generate function."""
    path = _MK_DIR / "adapters" / f"{name}.py"
    unique_name = f"mk_adapters_{name}"

    # Ensure the memory-kit parent dir is on sys.path so the adapter's
    # own imports (e.g. 'from adapters.utils import ...') resolve.
    mk_parent = str(_MK_DIR)
    if mk_parent not in sys.path:
        sys.path.insert(0, mk_parent)

    spec = importlib.util.spec_from_file_location(unique_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod.generate


def make_wrapper(name: str):
    """Return a generate(project_root, config=None) function backed by the named memory-kit adapter."""
    _generate = None

    def generate(project_root: Path, config = None):
        # config: dict | None — using Optional to avoid 3.9 union syntax error
        nonlocal _generate
        if _generate is None:
            _generate = load_adapter(name)
        if config is None:
            import yaml
            config_path = project_root / ".agent" / "project.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)
        return _generate(project_root, config)

    return generate
