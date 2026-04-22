# Gemini CLI Context

This project uses a shared memory system in the `memory/` directory:

- `memory/semantic.md` — project knowledge (read at session start)
- `memory/working.md` — current task state (read every turn)
- `dev/[task]/` — active task context

See `GEMINI.md` for full integration details.
