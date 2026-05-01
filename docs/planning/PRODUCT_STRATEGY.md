# applycling Product Strategy

*Working product strategy. Last reframe: 2026-05-01. This is not shipped
architecture; it records the current product thesis, the bets we are running,
and — equally important — the bets we have explicitly killed so we do not
re-litigate them by accident.*

## Product Thesis

applycling is a **package engine with two front doors**:

- A **hosted Telegram-first product** for normal users — forward a job link
  to a Telegram bot, get a ready-to-send package back in the same chat.
- An **MCP server** for agent-native power users who already live inside
  Claude Desktop, Cursor, Hermes, Codex, or similar hosts.

Everything else (tracker, CLI ergonomics, generic gateway middleware, Hermes-
as-runtime, additional channels) is in service of one of those two doors or
it does not ship.

The strongest product promise remains:

> Forward any job link to applycling. It returns the application package you
> should send.

## ICP

**Primary:** the *heavy applicant* — sending 5+ tailored applications per
week. Bootcamp grads, career switchers, layoff cohorts, international job
seekers chasing volume. They feel the pain weekly, edit less than perfectionists,
and tolerate rough edges if applycling saves an hour per app.

**Not the ICP (yet):** staff+ engineers doing 4 careful applications per year
(too low frequency to form a habit), career coaches (different product —
multi-tenant review tooling), enterprise outplacement (sales-led, wrong
motion for this stage).

Every product decision is judged against the heavy applicant. If a feature
helps the staff engineer but slows the heavy applicant's loop, it loses.

## Quality Bar (the only metric that matters now)

**Send rate without major edits.** Target: >70% of generated packages sent
with only light copy-edits.

If we are not hitting that on our own usage, no distribution bet matters —
the engine is a fancy starting prompt, not a product. Fix the engine first.

Secondary signals (lagging): regenerate count per job, time from URL to
"sent" status, package abandonment rate.

We instrument these on dogfood usage before adding any new intake surface.

## Why This Matters

Job discovery is fragmented (LinkedIn, company sites, recruiter email,
friends, group chats, mobile browsing). LinkedIn's native job tracker owns
one slice of *tracking*; it does not generate packages and is not a competitor
for what applycling actually does.

The opening is to make application generation **ambient** — the user
forwards a link from where they already are, and a package comes back. The
runtime has to live somewhere the user does not manage: on our server, or
inside an agent host they already run.

## Strategic Bets (We Are Running These)

### Bet A — Hosted SaaS, Telegram-first intake

A hosted instance whose primary intake is a single Telegram bot
(`@applycling_bot`). One bot, many users. Server runs the pipeline, server
holds the keys, packages come back as PDFs in the same chat with a web
review link.

**How it works:**

- Web signup, paste resume / upload.
- Web flow shows a "Connect Telegram" button → deep link
  `https://t.me/applycling_bot?start=<token>`.
- User opens Telegram, taps Start, the bot binds their `chat_id` to the
  account on first message. Identity solved with no OAuth, no gateway.
- User sends or forwards a job URL to the bot.
- Bot streams progress ("fetching JD…", "tailoring resume…"), then sends
  PDFs + a web review link.
- Inline replies: `/regenerate`, `/refine more emphasis on X`,
  `/sent` to mark the application sent.
- Web review surface remains for editing, side-by-side artifact view, and
  package history.

**Why Telegram (not email, Discord, Slack, WhatsApp):**

- Mobile-native, where group-chat job links and "hey check out this role"
  forwards actually live.
- Bot API is mature, free, and we have already validated the intake loop
  via the Hermes-as-gateway dogfood.
- Identity via `chat_id` + `/start <token>` deep link is as clean as
  email plus-addressing — no account-linking swamp.
- Interactive: follow-ups (`/regenerate`, `/refine`) are natural in chat,
  awkward in email.
- File attachments work both ways and render inline on mobile.
- Email is *not* the wedge in 2026 — heavy applicants are not living in
  inbox; they are in chat, on mobile, while browsing.
- Discord, Slack, WhatsApp are explicitly deferred (see kill list) so we
  do not turn this into a multi-channel problem on day one.

**Onboarding lane (5 steps, browser → Telegram):**

1. Sign up on web.
2. Paste resume / upload.
3. Tap "Connect Telegram" → deep link.
4. Send a job URL to the bot.
5. Receive package in chat.

No agent install, no CLI, no API keys, no bot tokens to manage on the
user's side.

**If this bet is wrong:** we spent a quarter on auth, billing, abuse
mitigation, and a Telegram surface that the local product did not need.
Containable; the engine is reusable in either direction.

**Decision gate:** ship to 10 dogfood/paid users. If <50% hit "package
sent" within their first 3 forwards, the bet is failing — fix the engine,
the resume parsing, or the in-chat review flow before adding channels.

### Bet B — MCP server for agent-native power users

Ship `applycling mcp serve`. Tools map 1:1 to pipeline capabilities
(`add_job`, `list_jobs`, `get_package`, `interview_prep`, `refine_package`).

**Audience:** the ~10k engineers already running Claude Desktop, Cursor,
Codex, Hermes. They install via `pipx`, drop in MCP config, and applycling
shows up as tools inside the agent they already use.

**Onboarding lane (power-user, 4 steps):**

1. `pipx install applycling`
2. `applycling setup` (resume, profile, provider key)
3. Add MCP entry to client config.
4. Talk to the agent.

**Why this is cheap to do alongside Bet A:**

- The pipeline is already library-first; MCP is a thin protocol shim.
- It is the prerequisite for any agent-host integration (Hermes skill,
  Claude Desktop skill, Cursor command). Write the protocol once; every
  agent host is a one-page wrapper.
- Remote MCP (hosted, OAuth) is the natural bridge from Bet B back into
  Bet A within ~6 months — same engine, agent-host front door.

**If this bet is wrong:** the audience is too small to matter and we have
been polishing a niche tool. Still useful internally as the dogfood path.

**Decision gate:** does at least one non-author, non-Hermes user adopt MCP
through Claude Desktop or Cursor and run >5 packages without help?

## How Hermes (and Other Agent Hosts) Fit

Hermes-skill vs MCP is a **false binary**. We pick MCP as the capability
interface and write a 1-page Hermes skill that points Hermes at those tools.
Same approach for Claude Desktop, Cursor, Codex.

- **MCP server** = stable contract over `pipeline.run_add` and friends.
  One artifact, owned by us.
- **Hermes skill** = ~50 lines of markdown saying "to handle job URLs,
  call these MCP tools."
- **Claude Desktop / Cursor / Codex** = same shape, different host config.

Hermes stays a high-quality power-user path and our internal dogfood, but
it is not a required dependency for end users and it is not a runtime we
own. We do not build a Hermes-native plugin that reaches into Python — that
forks our own engine.

## What We Are Killing (Do Not Re-Litigate)

This section exists so we do not silently rediscover and reconsider these
ideas. If a future change wants to revive any of them, append a supersession
to `DECISIONS.md` first and explain what changed.

### Killed: applycling as a tracker-first product

LinkedIn's native job tracker, Teal, Huntr, and Simplify already cover
status tracking. Tracking in applycling exists only as **package history**
— the artifact state attached to each generated package. We do not build
kanban views, reminder systems, or a tracker brand. *Killed because:*
commoditized surface; we have no advantage; it distracts from the engine.

### Killed: Hermes-per-user as the consumer onboarding path

Requiring each end user to install Hermes, set up a profile, manage launchd
plists, and supply DeepSeek/provider keys is not consumer onboarding. Hermes
remains valid for our own dogfood and the power-user lane. *Killed because:*
the runtime lives in the wrong place — on the user's machine, managed by
the user. Onboarding cliff is too tall.

### Killed: Generic multi-channel gateway middleware (Chatwoot, n8n, Activepieces, Matrix, ClawScale, etc.)

We do not adopt or evaluate any abstract "messaging gateway" layer that
tries to unify multiple channels behind one API. The Telegram Bot API is
called directly from our server. *Killed because:* every gateway carries
its own product and operational footprint; abstracting over channels
before we know which channels matter is premature optimization with high
blast radius. (Note: this kills *gateway middleware*, not messaging itself
— messaging via Telegram is Bet A.)

### Killed: Email as a v1 intake channel

Email forwarding to `user+token@applycling.app` was considered and rejected
as the primary intake. *Killed because:* the ICP (heavy applicant in 2026)
lives in mobile chat, not inbox. Email is non-interactive (no
`/regenerate`, no streamed progress), feels like a 2015 product surface,
and would require us to own deliverability, spam reputation, and inbound
parsing infrastructure for a channel the user does not actually want to
use. Revisit only if Telegram intake proves the loop and a specific user
segment (e.g. recruiters forwarding role descriptions) demands email.

### Killed: Discord, Slack, WhatsApp as v1 intake channels

Discord adds server-vs-DM identity complexity; Slack is enterprise-only
and wrong for the heavy-applicant ICP; WhatsApp has Meta business-API
gatekeeping and per-message costs. None ship until Telegram has proved
the loop and there is concrete user-pull evidence for adding a second
channel.

### Killed: "shared bot, magical sender-ID profile resolution" (the original naive form)

The original "everyone DMs one bot, it just knows who you are from your
sender ID" model is replaced with the explicit `/start <token>` deep-link
binding flow. The user *must* sign up on web first; the bot binds their
chat to the existing account on first interaction. *Killed because:*
implicit profile resolution from sender ID is a privacy/abuse footgun and
hides the fact that an account must exist. The deep-link flow keeps the
"one bot, many users" magic without the multi-tenant gateway swamp.

### Killed: CLI as the primary user surface (softened 2026-05-01)

CLI stays as the developer/power-user/dogfood interface and is a first-class
caller of `pipeline.run_add()`. It is **not** a target for end-user
onboarding investment. We do not build `applycling tui`, an interactive
setup wizard for normies, or a `homebrew` tap before the hosted product
ships. *Killed because:* the CLI has the same install-cliff disease as
Hermes — terminal, `pip`, API keys, `data/profile.json` editing. Wrong
front door for the ICP.

*2026-05-01 update:* The CLI remains the canonical product surface during
pre-user validation (we ship nothing before the engine quality bar is met).
MCP server is the bridge to agent-host power users; Telegram bot is the
bridge to normal users. Neither replaces the CLI during solo development.

### Killed: "Improve quality" as a goal without a metric

We do not ship prompt-engineering or skill changes justified by "this should
make outputs better." Every quality change is judged against **send rate
without major edits**, instrumented on dogfood usage. *Killed because:*
unmeasured quality work expands forever and never closes.

### Killed (for now): Multi-tenant SaaS with team/org features

Career coaches, outplacement firms, and recruiter platforms are not the
ICP. We do not build org accounts, seat-based billing, or coach-review
workflows until the single-user heavy-applicant loop is healthy. Bet C
(API/MCP for other career tools) is **deferred, not dead** — revisit only
after Bet A has paying users.

## Onboarding Principle

Two lanes, no forced upgrade between them:

- **Normal lane (Bet A):** hosted profile + Telegram bot + web review.
  Browser for signup, Telegram for daily use. No agent, no CLI, no keys.
- **Power-user lane (Bet B):** local install + MCP into the user's
  existing agent host. User-owned keys and data.

Every concept the user must learn before their first successful package is
an activation tax: agents, profiles, gateways, model keys, launch agents,
bot tokens, MCP JSON, local daemons, provider selection. Hide them unless
the user has already chosen the power-user lane.

## Near-Term Direction

1. **Now → 2 weeks:** Ship MCP server (`applycling mcp serve`). Cheap,
   unblocks Bet B, and is the prerequisite for any agent-host wrapper.
2. **Now → 4 weeks:** Instrument send-rate / edit-rate / regenerate-count
   on our own usage. If <70% send-without-major-edits, freeze new surface
   work and fix the engine.
3. **Once MCP ships:** Write the Hermes skill as a 1-page MCP wrapper.
   Confirms the layering works. ~1 day of work.
4. **Next quarter:** Hosted lane with Telegram-bot intake as v1. Web
   signup → resume paste → "Connect Telegram" deep link → bot binds
   `chat_id` → user forwards URLs in chat → packages return as PDFs +
   web review link.
5. **Defer:** every other channel (email, Discord, Slack, WhatsApp),
   every gateway middleware evaluation, every tracker enhancement, every
   team/org feature.

## 2026-05-01 Reframe — Post Hosted Dogfooding Sprint

After shipping the hosted dogfooding sprint (20/20 gates, Hermes on VPS,
end-to-end Telegram → generation → artifacts), we re-examined the thesis.

### What We Learned

Building hosted Hermes as a single-user convenience layer took ~2 weeks of
infrastructure and setup pain (env vars across multiple files, competing
gateways, DeepSeek key wrangling). The result works for one person but
exposes exactly zero path to add users — multi-user requires `users` table,
per-user profiles, data isolation, and onboarding, none of which exist.

LinkedIn's native job tracker covers the status-checking use case. The
differentiator is the generation engine — not the bot, not the tracker.

### Refined Strategy

**CLI is the foundation.** The pipeline is library-first. `pip install
applycling` + `applycling run <url>` always works. Every other surface
(Telegram, MCP, web) is a thin caller of the same pipeline. We do not
build SaaS infrastructure for one user.

**Telegram is a multi-user surface, not a single-user convenience.**
The hosted Hermes that exists today is an Amirali-only bridge. The real
Telegram product requires multi-tenant identity (telegram_id → user
mapping), per-user data, and an MCP toolset that scopes Hermes to exactly
three functions: create_job, get_status, get_artifact. No terminal access,
no secrets exposure, no cross-user data leaks. See `vision.md` §5
"Multi-User Architecture" for the full proposal.

**Multi-user ships when there are users.** Not before. The infrastructure
is documented and the path is clear, but buying SaaS complexity before
validation is the wrong trade.

### What This Changes in the Strategy

- Bet A (hosted Telegram) is NOT killed, but is re-scoped: it ships when
  we have users to onboard, not as a solo dogfood deployment.
- The "Killed: CLI as primary user surface" entry below is softened:
  the CLI remains the canonical product surface during pre-user validation.
  MCP server and Telegram bot are additive, not replacements.
- Next immediate action: ship the MCP server (`applycling mcp serve`)
  as the protocol shim that both the CLI power-user lane and the future
  Telegram multi-user lane share.

## Decision Gates

**For Bet A (hosted Telegram):** 10 dogfood/paid users; >50% reach "package
sent" within 3 forwards; engine quality bar holding (>70% send-without-
edits).

**For Bet B (MCP):** at least one non-author user adopts via Claude
Desktop or Cursor and runs >5 packages unaided.

**For reviving anything in "What We Are Killing":** append a supersession
to `DECISIONS.md` naming what changed in the world. Do not silently
restart work on a killed bet.

## Positioning

Short:

> applycling turns job links into ready-to-send application packages.

Expanded:

> Forward any job posting — from a recruiter email, a LinkedIn link, a
> company career page — to applycling. It uses your profile and history
> to generate a tailored resume, cover letter, positioning brief, outreach
> note, and fit summary, then keeps the package attached to that
> opportunity for review and follow-up.
