# Response to Review

## What I accept

**Funnel logic is weak.** The OSS audience (agent-native hackers) and Workbench audience (job-searchers) are disjoint. "pipx install applycling" reaches 10× more people than "drop skills into your Hermes directory." The agent-native architecture is elegant but limits reach. This is the same mistake the prototype made — building for the architecture, not the user.

**"Skills are the moat" + MIT = contradiction.** Either skills aren't the moat (the moat is Workbench UX/tracker/data), or the license isn't MIT (use BSL/source-available). Can't have both.

**MCP is missing entirely.** We just shipped MCP-T1–T5. Where does it live?

**Tracker writes break "one engine, no fork."** If the orchestrator doesn't know about a tracker, Workbench must wrap it → two orchestrators → drift.

**Workday scraping with curl won't work.** Most common ATS, JS-rendered. First impression for OSS users will be a crash.

**Eval gate too small.** 20 × 1 is noisy for LLM nondeterminism. Should be 20 × 3.

**Wire Workbench in 1 hour is unrealistic.** Days, not hours.

**Profiles, time estimates, copy-paste errors** — all valid.

## What I'd push back on

**Working memory conflict.** The strategy doc doesn't mean "ship paid SaaS tomorrow." It means "this is the long-term two-product architecture." The sequencing should be: ship OSS first (solo alpha, per working memory), validate, then add Workbench later. The strategy doc should make this explicit.

**Submodule debate.** For solo alpha, the review is right — submodules are overkill. Shell out is simplest. But the execution doc should pick one and justify it.

**"Workbench" naming.** Fair that it sounds like an IDE plugin. But "Cloud" or "SaaS" are worse. Keep Workbench or go with "applycling Pro."

## The core insight I missed

I was doing the same thing I criticized the prototype for — building for an elegant architecture (agent-native) instead of building for the user. The agent-native path reaches a tiny intersection. A CLI reaches anyone with a terminal. A web app reaches anyone with a browser.

## Unresolved questions (for tomorrow)

1. Does this supersede or coexist with the messaging-alpha-first strategy in working memory?
2. Where does MCP live — public repo, private, or both?
3. Shell out, submodule, subtree-split, or published package?
4. MIT or source-available license?
5. Agent-native via Telegram, pipx-installable CLI, or web app as the primary OSS surface?
