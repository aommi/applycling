# Two-Product Strategy — Planning Directory

## Status: Under Review

The strategy has been drafted, reviewed by an external agent, and received a response. Five open questions need resolution before Phase 1 begins.

## Files

| File | What |
|------|------|
| `TWO_PRODUCT_STRATEGY.md` | The pitch: why two products, one engine |
| `TWO_PRODUCT_EXECUTION.md` | The plan: phases, eval gate, architecture |
| `applycling-two-products.pptx` | 10-slide deck for the proposal |
| `build_deck.js` | pptxgenjs script that generated the deck |
| `REVIEW.md` | External agent review — critical analysis |
| `RESPONSE.md` | My response — what I accept, what I push back on |

## Key Tensions

1. **Agent-native vs CLI as distribution.** The current strategy optimizes for agent-native (Hermes + Telegram) because it's architecturally elegant. But a `pipx install applycling` CLI reaches 10× more users. Same skills, different surface.

2. **Funnel vs separate products.** The strategy pitches OSS as a funnel into Workbench. But the OSS audience (agent-native hackers) and Workbench audience (job-searchers who want a dashboard) are mostly disjoint. The OSS version may be a separate product for a separate audience, not a funnel.

3. **"Skills are the moat" vs MIT license.** Can't claim skills are the moat and then MIT-license them. Either the moat is Workbench's UX/tracker/data (keep MIT), or the license is BSL/source-available (skills are the moat).

4. **Working memory conflict.** `memory/working.md` says disciplined solo alpha, paid product deferred. The strategy doc implies paid SaaS now. Needs reconciliation.

## Open Questions (for next session)

1. Does this supersede or coexist with the messaging-alpha-first strategy?
2. Where does MCP live?
3. Shell out, submodule, subtree-split, or published package?
4. MIT or source-available license?
5. Agent-native via Telegram, pipx-installable CLI, or web app as the primary OSS surface?
6. Do we need a pipx-installable CLI in addition to or instead of agent-native?
