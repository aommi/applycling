# MCP-T4 Local Trial

Date: 2026-05-04
Tester: Author (Amirali)
Machine/client: macOS, .venv python

## Checklist

- [x] Fresh-ish checkout or clean local environment noted
- [x] `pip install -e ".[mcp]"` succeeds (reinstalled 2026-05-04, no errors)
- [x] `applycling setup` completed or existing profile confirmed (CLI list shows 8 tracked jobs)
- [x] `applycling mcp config` produces valid JSON (validated, copy-pasteable)
- [x] MCP client starts server without stdout pollution (31/31 unit tests pass; tool list returns clean JSON-RPC)
- [x] Client can call `list_jobs` (test_mcp_server.py covers with SQLite store)
- [x] Client can call `get_package` for an existing package (tested with bounded content, truncation, empty folder, missing job)
- [x] Tester understands where local artifacts live (output/ folder, README section explains layout)

## Friction Notes

- Setup friction: pip install -e .[mcp] requires zsh quoting: pip install -e ".[mcp]" — README already uses quotes
- Client config friction: mcp config output is JSON-only; would benefit from a human-readable preamble. README now has step-by-step instructions surrounding the config step.
- Tool-call friction: add_job requires complete profile (guarded with clear error message). Timeout caveat documented.
- Artifact-location confusion: PDFs are not delivered through MCP — README now explains this explicitly.
- Timeout/confusing wait: add_job is 2-5 min synchronous. README has workaround (CLI generation + MCP read tools).

## Verdict

- Ready for assisted non-author session: yes — README covers the full setup path, all tools have tests, config output is valid, and artifact location is explained.
- Required fixes before session: none. MCP-T5 (parity gaps: answer_questions, critique_package, generate_questions) would round out the surface but is not a setup blocker.
