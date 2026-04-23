"""
Claude Code Adapter — thin wrapper around memory-kit adapter.
"""
from ._mk import make_wrapper

generate = make_wrapper("claude_code")
