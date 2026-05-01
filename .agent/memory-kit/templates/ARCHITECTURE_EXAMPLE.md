# {project_name} — Architecture Vision

*Canonical record of architectural principles, load-bearing assumptions, and planned
capabilities. This is NOT a current-state inventory — for what's built today, see
`memory/semantic.md`. For sprint plans and tickets, see planning docs.*

*If you are reading this for the first time, you should leave knowing: (1) what
the architecture IS committed to, (2) why, and (3) where it is going.*

---

## 1. Thesis

Replace this with a 2–4 sentence statement of what this system is, what it does,
and the core design bet you are making. This should be stable — if this changes,
the system has pivoted.

**Two-level vocabulary (define your key terms here):**
- **Term A** — definition
- **Term B** — definition

---

## 2. Design Commitments

List 2–4 permanent design choices that are not assumptions (they will not be
invalidated — they define what the system is). Example:

1. **Intelligence lives in skills, not the runtime.** The harness is plumbing;
   behavior lives in files.
2. **The pipeline is a library, not a CLI.** Every caller uses the same contract.

---

## 3. Assumptions

Load-bearing premises the architecture depends on. When one is invalidated,
append a supersession to `DECISIONS.md` and update or remove the assumption here.

**Test for inclusion:** would invalidating this force a rewrite of the core design?
If yes → here. If no → `DECISIONS.md`.

> **Assumption: [name]**
> Load-bearing because: [why the architecture depends on this being true]
> Invalidated when: [concrete condition that would falsify this premise]

---

## 4. Vision: Planned Capabilities

Describe planned capability areas without sprint labels or ticket numbers. Each
entry should name a capability, what it unlocks, and the key design constraint.

### [Capability name]

What it does and why it matters. Key design constraints or open questions.

---

## 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [describe risk] | Low/Medium/High | Low/Medium/High | [mitigation] |

---

## 6. How to Add a [Core Unit]

Step-by-step guide for the most common extension pattern (e.g., adding a new
pipeline step, adding a new skill, adding a new API endpoint).

---

## 7. What This Document Is Not

- Not a current-state inventory — see `memory/semantic.md`
- Not a sprint plan — see planning docs
- Not an API reference — see code docstrings
- Not a user guide — see `README.md`

If a change contradicts any section here, update this doc in the same commit.
