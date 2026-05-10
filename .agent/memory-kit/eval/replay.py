#!/usr/bin/env python3
"""Eval replay — measure whether saved memory context changes agent behavior.

TWO MODES:

  validate  — Check capture file format integrity.
  replay    — Compare a replayed run against its baseline capture.

USAGE:
  python eval/replay.py validate .agent/eval/captures.jsonl
  python eval/replay.py replay .agent/eval/captures.jsonl --line 3 \
      --buckets '["filesystem-read","code-edit","shell-exec"]'

INTENT BUCKETS normalize tool calls across harnesses so tool-name drift
(Claude Code renaming Bash → Shell, etc.) doesn't register as plan instability.

CAPTURE FORMAT (JSONL, one JSON object per line):
  {"memory_hash":"<sha256>","prompt":"...","buckets":["shell-exec",...],
   "timestamp":"...","harness":"claude-code"}

This script is diagnostic, not load-bearing. It helps the user answer
"did my memory system actually help?" but does not gate infrastructure decisions.
"""
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

# ── Intent-bucket mapping ────────────────────────────────────────────────────

BUCKET_MAP: dict[str, dict[str, str]] = {
    "claude-code": {
        "Bash": "shell-exec", "Read": "filesystem-read", "Write": "code-edit",
        "Edit": "code-edit", "Grep": "filesystem-read", "Glob": "filesystem-read",
        "WebSearch": "web-fetch", "WebFetch": "web-fetch", "Task": "agent-spawn",
        "NotebookEdit": "code-edit",
    },
    "codex": {
        "execute": "shell-exec", "read_file": "filesystem-read",
        "write_file": "code-edit", "edit_file": "code-edit",
        "search": "filesystem-read", "web_search": "web-fetch",
        "browser": "web-fetch", "task": "agent-spawn",
    },
    "hermes": {
        "terminal": "shell-exec", "read_file": "filesystem-read",
        "write_file": "code-edit", "patch": "code-edit",
        "search_files": "filesystem-read", "web_search": "web-fetch",
        "delegate_task": "agent-spawn", "browser_navigate": "web-fetch",
        "execute_code": "shell-exec",
    },
    "cursor": {
        "run_terminal_cmd": "shell-exec", "read_file": "filesystem-read",
        "write_to_file": "code-edit", "search_codebase": "filesystem-read",
        "web_search": "web-fetch", "task": "agent-spawn",
    },
    "gemini-cli": {
        "run_shell": "shell-exec", "read_file": "filesystem-read",
        "write_file": "code-edit", "search": "filesystem-read",
        "web_fetch": "web-fetch",
    },
}

KNOWN_BUCKETS = {"shell-exec", "code-edit", "filesystem-read", "web-fetch", "agent-spawn"}


def classify_tool(tool: str, harness: str) -> str:
    """Map a harness-specific tool name to a normalized intent bucket."""
    mapping = BUCKET_MAP.get(harness, {})
    if tool in mapping:
        return mapping[tool]
    # Fallback heuristic for unknown tools
    t = tool.lower()
    for keyword, bucket in [
        ("bash", "shell-exec"), ("shell", "shell-exec"), ("exec", "shell-exec"),
        ("terminal", "shell-exec"), ("run", "shell-exec"),
        ("read", "filesystem-read"), ("grep", "filesystem-read"),
        ("search", "filesystem-read"), ("glob", "filesystem-read"),
        ("ls", "filesystem-read"), ("cat", "filesystem-read"),
        ("write", "code-edit"), ("edit", "code-edit"), ("patch", "code-edit"),
        ("web", "web-fetch"), ("fetch", "web-fetch"), ("browser", "web-fetch"),
        ("spawn", "agent-spawn"), ("task", "agent-spawn"), ("delegate", "agent-spawn"),
    ]:
        if keyword in t:
            return bucket
    return "shell-exec"


# ── Validation ───────────────────────────────────────────────────────────────

def validate(jsonl_path: Path) -> dict:
    """Check capture file format integrity."""
    issues: list[str] = []
    valid = 0
    total = 0

    if not jsonl_path.exists():
        return {"valid": 0, "total": 0, "issues": ["file not found"]}

    with open(jsonl_path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                cap = json.loads(line)
            except json.JSONDecodeError as e:
                issues.append(f"line {lineno}: invalid JSON — {e}")
                continue

            missing = [k for k in ("memory_hash", "prompt", "buckets") if k not in cap]
            if missing:
                issues.append(f"line {lineno}: missing fields {missing}")
                continue

            if not isinstance(cap["buckets"], list):
                issues.append(f"line {lineno}: buckets is not a list (got {type(cap['buckets']).__name__})")
                continue

            unknown = [b for b in cap["buckets"] if b not in KNOWN_BUCKETS]
            if unknown:
                issues.append(f"line {lineno}: unknown bucket(s) {unknown}")

            valid += 1

    return {"valid": valid, "total": total, "issues": issues}


# ── Replay comparison ────────────────────────────────────────────────────────

def _hash_memory(project_root: Path) -> str:
    """SHA256 of current memory files."""
    h = hashlib.sha256()
    for rel in sorted(["memory/semantic.md", "memory/working.md", "DECISIONS.md"]):
        path = project_root / rel
        if path.exists():
            content = path.read_text()
            h.update(rel.encode())
            h.update(content.encode())
    return h.hexdigest()


def compare(
    jsonl_path: Path,
    line_num: int,
    replayed_buckets: list[str],
    project_root: Optional[Path] = None,
) -> dict:
    """Compare a replayed run against its capture baseline.

    Returns plan_stability (whether first bucket matches) and memory_delta
    (whether memory changed since capture).
    """
    if project_root is None:
        project_root = Path.cwd()

    captures: list[dict] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                captures.append(json.loads(line))

    if line_num < 1 or line_num > len(captures):
        return {"error": f"line {line_num} out of range (1..{len(captures)})"}

    cap = captures[line_num - 1]
    baseline_buckets = cap.get("buckets", [])
    current_hash = _hash_memory(project_root)

    first_stable = (
        baseline_buckets[0] == replayed_buckets[0]
        if baseline_buckets and replayed_buckets
        else None
    )
    memory_changed = current_hash != cap.get("memory_hash", "")

    from collections import Counter

    baseline_counts = Counter(baseline_buckets)
    replayed_counts = Counter(replayed_buckets)

    skipped: list[str] = []
    new_steps: list[str] = []
    all_buckets = set(baseline_counts) | set(replayed_counts)
    for b in sorted(all_buckets):
        diff = baseline_counts[b] - replayed_counts[b]
        if diff > 0:
            skipped.extend([b] * diff)
        elif diff < 0:
            new_steps.extend([b] * (-diff))

    return {
        "line": line_num,
        "prompt": cap.get("prompt", ""),
        "harness": cap.get("harness", "unknown"),
        "plan_stability": {
            "first_bucket_stable": first_stable,
            "baseline_first": baseline_buckets[0] if baseline_buckets else None,
            "replayed_first": replayed_buckets[0] if replayed_buckets else None,
        },
        "redundant_avoided": {
            "steps_skipped": sorted(skipped),
            "steps_skipped_count": len(skipped),
            "new_steps": sorted(new_steps),
        },
        "memory_delta": {
            "changed": memory_changed,
            "baseline_hash": cap.get("memory_hash", ""),
            "current_hash": current_hash,
        },
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "validate":
        if len(sys.argv) < 3:
            print("Usage: python eval/replay.py validate <captures.jsonl>")
            sys.exit(1)
        result = validate(Path(sys.argv[2]))
        print(f"Valid: {result['valid']}/{result['total']}")
        if result["issues"]:
            print("\nIssues:")
            for issue in result["issues"]:
                print(f"  - {issue}")
            sys.exit(1)

    elif cmd == "replay":
        if "--line" not in sys.argv or "--buckets" not in sys.argv:
            print("Usage: python eval/replay.py replay <captures.jsonl> "
                  "--line <N> --buckets '[...]'")
            sys.exit(1)
        jsonl_path = Path(sys.argv[2])
        line_idx = sys.argv.index("--line")
        line_num = int(sys.argv[line_idx + 1])
        buckets_idx = sys.argv.index("--buckets")
        replayed = json.loads(sys.argv[buckets_idx + 1])
        result = compare(jsonl_path, line_num, replayed)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "buckets":
        # Print the intent-bucket mapping for reference
        print(json.dumps(BUCKET_MAP, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
