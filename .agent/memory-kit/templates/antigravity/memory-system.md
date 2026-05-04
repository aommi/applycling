# Memory System — {project_name}

You are working on a project with a file-based persistent memory system.
Follow these rules on every turn.

## Session Start
Read `memory/semantic.md` ONCE to load distilled project context.

## Every Turn
Read `memory/working.md` to know the current task state before responding.

## Task Files
Only load `/dev/[task]/*` files when actively working on that specific task.
Do not speculatively load files "just in case".

## MCP Efficiency
Before calling any MCP tool to retrieve project information, first check if
that information might exist in `memory/semantic.md` or `dev/[task]/context.md`.
Local files are cheaper than remote MCP queries.

## Context Drift
If your reasoning becomes uncertain or inconsistent with prior context,
re-read `memory/semantic.md` before continuing.

## Task Switching
If the user's message describes work outside the current `working.md` focus,
ask: "This looks like a different task — should I archive the current state first?"

{approval_gate}
