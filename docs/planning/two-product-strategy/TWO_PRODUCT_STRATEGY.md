# applycling — Two Products, One Engine

## The Pitch

applycling turns a job URL into a tailored application package. There are two ways to use it.

### applycling (open source, agent-native)

Send a job URL to your agent. Get back a tailored resume, cover letter, positioning brief, email — everything. No signup, no dashboard, no monthly fee. You already have an agent. This gives it the skills.

```
Telegram → "apply to https://jobs.lever.co/company/role"
         → agent scrapes, generates, packages
         → PDFs delivered back in Telegram
```

One command to install. Zero infrastructure. Works on any agent runtime (Hermes, Claude Code, OpenClaw). Fork it, tweak the cover letter style, contribute back.

### applycling Workbench (hosted SaaS)

Everything in the open source version, plus: a web dashboard that tracks every application, a workbench to review and regenerate packages, job status history, analytics on what's getting responses. For people who are running a job search, not just applying to one role.

$X/month. Built on the same skills and tools as the open source version.

## Why This Works

**Open source is the funnel.** Someone tries applycling for free, gets a great cover letter in 30 seconds. They apply to 8 jobs. They think: "I want to see all of these in one place." They become a Workbench customer — not because they were sold to, but because they organically outgrew the free version.

**The skills are the moat.** 18 markdown files — 17 content skills plus an orchestrator — that encode years of application-writing judgment. The open source version keeps them sharp: users fork, tweak, and contribute improvements. Every improvement benefits both products.

**Agent-native is the distribution.** No app store, no npm install, no deployment. Users who already run an AI agent get applycling by dropping a folder into their skills directory. The install is one command. The "UI" is a conversation.

**Fat skills, sharp tools, thin harness.** The orchestrator skill describes what to do and when. The 17 content skills do the LLM work. The deterministic tools (scrape, clean, render, assemble) handle repeatable execution. The agent runtime (Hermes) is the harness — tool calling, file I/O, error handling. Nothing gets reinvented.

**One engine, no fork.** The orchestrator lives in the public repo. Whether an agent executes it directly or Workbench's Python code invokes the same tools in the same sequence, the policy is in one place. No two-engines drift.

## What It's Not

Not a "freemium" play where the free version is crippled. The open source version turns a URL into a complete application package — no limits. The SaaS adds things the free version genuinely can't do without infrastructure: persistent tracking, visual workbench, multi-job management, analytics.

People who only need the core engine never need to pay. People who need the workbench want to pay. Clean line.

## Architecture Decision

The pipeline orchestrator is a skill, not Python code. It describes: what steps to run, in what order, what files to produce, when to skip, how to retry, when to ask the user. The agent runtime executes it.

If the orchestrator skill proves too brittle (agents improvise file names, skip steps, produce inconsistent output), the fallback is a thin Python wrapper that calls the same tools but enforces deterministic structure. That decision comes from running 20 real URLs through it and measuring consistency.

*Written 2026-05-06. Supersedes the earlier "extract Python engine" approach — the orchestrator IS a skill.*
