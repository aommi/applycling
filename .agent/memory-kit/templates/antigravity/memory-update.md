# Memory Update

Run this workflow after completing significant work to update project memory.

## Steps

1. Inspect the git diff:
   - `git diff --name-only`
   - `git diff` for specifics when needed

2. If the reason behind a change is not obvious from the diff, ask the user
   for intent before proposing any memory update. Do not guess intent from code alone.

3. Evaluate whether changes introduce any of:
   - New architectural decisions
   - New patterns or conventions
   - Important implementation details worth remembering
   - Bugs or gotchas discovered during work
   - Resolved assumptions (from `dev/[task]/context.md` Assumptions section)

4. If ANY qualifies as architecturally or operationally significant:
   - Draft the proposed update — show the user exactly what would be written and to which file
   - Wait for explicit approval ("looks good", "yes", "approve") before writing
   - On approval: write to `semantic.md` and/or `DECISIONS.md` and/or `context.md`
   - On correction: apply the user's edit, then write

5. Always, regardless of significance:
   - Update `memory/working.md` to reflect current state — this does NOT require approval
   - If `working.md` is stale, inconsistent, or over 300 lines: rewrite from scratch

6. If changes are trivial (renames, formatting, one-line bugfixes without broader lessons):
   - Update `working.md` only
   - State explicitly: "No semantic.md update needed — changes were trivial."
