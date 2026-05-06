# Agent Review — Two-Product Strategy

*Reviewed 2026-05-06 by a cold agent. Read both strategy + execution docs and working memory.*

## Precondition: working memory conflict

`memory/working.md` says: "ambition mode is explicit: disciplined solo alpha. Paid product discovery is a follow-on gate; pricing/business model stays lightweight until before public messaging beta."

`TWO_PRODUCT_STRATEGY.md` says: ship a free OSS funnel + paid Workbench SaaS now, with "$X/month" subscription.

These aren't compatible. Resolve before continuing.

## 1. Is the two-product strategy sound?

Partially. The free/paid line is drawn at a natural boundary (stateless package generation vs. stateful job-search management). That part is good.

But the funnel logic is weak. The OSS audience is "person who already runs a self-hosted agent (Hermes/OpenClaw), has Telegram wired to it, has pandoc + wkhtmltopdf installed, and wants help applying to jobs." That's a tiny intersection. The SaaS audience is "person running a job search who wants a dashboard." These are mostly disjoint personas — OSS hackers don't typically pay for SaaS dashboards, and job-searchers don't run agent runtimes.

The OSS version isn't crippled, but it's also not a credible funnel into Workbench. It's a separate product targeting a separate audience.

The "skills are the moat" claim contradicts the MIT license. If skills are the moat, MIT-licensing them hands the moat to anyone who wants to wrap their own SaaS around them. Either skills are the moat (then BSL/Elastic-style source-available, not MIT) or they aren't (then the moat is Workbench's UX/tracker/data, and the OSS pitch needs to stop calling skills the moat).

## 2. Execution plan gaps

- **MCP is missing entirely.** We just shipped MCP-T1–T5. Where does the MCP server live — public, private, or both? The biggest gap.
- **"Wire Workbench (1 hour)"** is wildly optimistic. Workbench's current orchestrator is Python with tracker writes interleaved across pipeline steps. Replacing it with "shell out to public tools" is days, not hours.
- **Profile schema not specified.** PROFILE-T1 established schema_version, one-profile-per-user, tracks-as-variants. The OSS profile.json template needs to match or there are two profile schemas immediately.
- **Tracker writes.** Does the orchestrator skill in OSS know about a tracker? If yes, OSS depends on the SaaS DB. If no, Workbench must wrap the orchestrator with tracker calls → Workbench has its own orchestration logic → contradicts "one engine, no fork."
- **Eval gate too small.** 20 URLs × 1 run is too small for measuring LLM-skill nondeterminism. Should be 20 × 3 minimum.
- **Workday scraping with curl+readability won't work.** Workday is JS-rendered. The most common ATS fails on first impression.
- **No license analysis for skill content.**
- **No telemetry / feedback loop for OSS.** If skills improve from "users fork, tweak, contribute back," there needs to be a path for that.
- **Two applycling/SKILL.md entries** in the tree diagram — copy-paste error.
- **Prompt says "submodule" but execution doc says "shell out."** Different mechanisms, different failure modes.

## 3. Submodule

The execution doc doesn't pick submodules — it picks "shell out." For submodules: drift risk, merge conflicts minimal if discipline holds, CI gap (public repo's eval needs to run on Workbench bumps), clunky for solo dev. For solo alpha, shell out + path-based skill loading is fine, submodule is overkill.

## 4. Naming

"applycling Workbench" is OK but inverted from convention (usually OSS gets the suffix, SaaS gets the bare brand). "Workbench" doesn't communicate "hosted job-search tracker" — sounds like an IDE plugin. Consider "applycling Cloud" or just "applycling.com."

## 5. Better architecture?

Monorepo with two publishable artifacts simpler than two repos for solo dev. Or git subtree split. Or pipx-installable CLI reaches 10× the audience of "agent-native."

## 6. Biggest risk

Distribution mismatch. You're optimizing the OSS product for the agent-native crowd because that's the architecture you find elegant, not because that's where Workbench customers come from. If this fails in 6 months, the post-mortem will read: "we shipped an OSS tool to a tiny audience that didn't convert, while the actual paid customers were people who'd never heard of Hermes and just wanted a CLI or a web app."

Second: maintenance overhead on a solo alpha. OSS issues and "it doesn't work on Workday" bug reports will eat the time you said you wanted to spend on the messaging alpha.

## Open Questions

1. Does this supersede the messaging-alpha-first strategy in working memory, or coexist with it?
2. Where does MCP live?
3. Submodule, shell-out, or subtree-split?
4. License: MIT or source-available?
5. Is "agent-native via Telegram + Hermes" really the OSS surface, or would a pipx-installable CLI reach 10× more users?
