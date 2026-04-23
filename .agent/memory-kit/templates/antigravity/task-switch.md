# Task Switch

Use this workflow when the user wants to change tasks mid-session.

## Steps

1. Confirm with the user: "Should I archive the current state first?"
2. If yes:
   - Snapshot current `memory/working.md` contents into `dev/[current-task]/context.md`
   - Create or load `dev/[new-task]/` folder
   - Read `dev/[new-task]/plan.md`, `context.md`, and `tasks.md`
   - Rewrite `memory/working.md` for the new focus
3. If no:
   - Simply create or load `dev/[new-task]/` and update `working.md`
