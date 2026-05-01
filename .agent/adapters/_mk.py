"""
Memory-kit dispatcher — loads parameterized adapters from .agent/memory-kit/
with proper package context for relative imports.
"""
import importlib.util
import sys
from pathlib import Path

_MK_DIR = Path(__file__).parent.parent / "memory-kit"
_ADAPTERS_DIR = _MK_DIR / "adapters"

# Ensure memory-kit is a package with __init__.py present
(_MK_DIR / "__init__.py").touch(exist_ok=True)
(_ADAPTERS_DIR / "__init__.py").touch(exist_ok=True)

# Register the memory-kit as a package in sys.modules so relative imports work
_mk_spec = importlib.util.spec_from_file_location(
    "memory_kit", _MK_DIR / "__init__.py"
)
_mk_mod = importlib.util.module_from_spec(_mk_spec)
sys.modules.setdefault("memory_kit", _mk_mod)

_adapters_spec = importlib.util.spec_from_file_location(
    "memory_kit.adapters", _ADAPTERS_DIR / "__init__.py"
)
_adapters_mod = importlib.util.module_from_spec(_adapters_spec)
sys.modules.setdefault("memory_kit.adapters", _adapters_mod)


def load_adapter(name: str):
    """Load a memory-kit adapter module and return its generate function."""
    path = _ADAPTERS_DIR / f"{name}.py"
    full_name = f"memory_kit.adapters.{name}"

    if full_name in sys.modules:
        return sys.modules[full_name].generate

    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    _mk_mod.adapters = _adapters_mod  # stitch package hierarchy
    spec.loader.exec_module(mod)
    return mod.generate


def make_wrapper(name: str):
    """Return a generate(project_root, config=None) function backed by the named memory-kit adapter."""
    _generate = None

    def generate(project_root: Path, config=None):
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
