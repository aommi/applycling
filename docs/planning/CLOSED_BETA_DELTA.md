# Closed Beta Delta — Gaps from Hosted Dogfood

**Date:** 2026-04-29
**Source sprint:** `docs/planning/HOST_DOGFOODING_SPRINT.md`

This document captures the remaining work needed to move from single-user hosted
dogfood to a closed beta or private-beta launch.

---

## 1. Multi-User Support

| What | Status | Notes |
|---|---|---|
| User registration / invite flow | Not started | Need signup, invite codes, or admin-managed accounts |
| Multi-user UI | Not started | Job board must scope to authenticated user |
| Tenant isolation | Not started | `pipeline_runs` uses `user_id` — verify DB-level isolation |
| Password reset / account lifecycle | Not started | Self-service password reset, account deactivation |

## 2. Auth & Security

| What | Status | Notes |
|---|---|---|
| Proper auth system (JWT, sessions) | Not started | Basic Auth is dogfood-only. Need real auth for beta |
| Rate limiting | Not started | Per-user rate limits for pipeline runs |
| CORS policy | Not started | Currently open — restrict for production |
| HTTPS enforcement via HSTS | Not started | Caddy can add HSTS header |
| Audit logging | Not started | Track who ran what pipeline, when |

## 3. Infrastructure

| What | Status | Notes |
|---|---|---|
| Object storage for artifacts | Not started | Local disk works for 1 user. S3/R2 needed for multi-user |
| Automated backups | Not started | Scheduled pg_dump + artifact sync to object storage |
| CI/CD pipeline | Not started | GitHub Actions → VPS deploy |
| Zero-downtime deploys | Not started | Blue/green or rolling deploy |
| Log aggregation | Not started | Ship logs to a service (Datadog, Grafana, etc.) |
| Monitoring / alerting | Not started | Alert on /healthz failures, OOM, disk usage |
| Multi-region / HA | Not started | Single VPS is SPOF |

## 4. Pipeline & Generation

| What | Status | Notes |
|---|---|---|
| Per-step heartbeat | Not started | Current heartbeat is before/after only. Per-step requires pipeline callback hooks |
| Cancellation | Not started | Mid-generation cancel button |
| Queue / worker pool | Not started | Beyond active-run guard — concurrent runs per user |
| Pipeline versioning | Not started | Track which skill version produced which artifacts |
| Model cost tracking | Not started | Per-run token usage and cost attribution |

## 5. UX & Features

| What | Status | Notes |
|---|---|---|
| User contexts in DB | Not started | Currently file-backed `data/`. Move to DB for multi-user |
| Sync+steering on web UI | Not started | CLI-only interactive mode today. WebSocket steering is future work |
| Interview prep enhancements | Not started | Question bank, practice mode, STAR answer generation |
| Job import from LinkedIn/Indeed | Not started | Manual URL paste only today |
| Mobile app / PWA | Not started | Mobile web works but no offline support or push notifications |
| Analytics dashboard | Not started | Application funnel, response rates, timeline |

## 6. Operations & Compliance

| What | Status | Notes |
|---|---|---|
| Terms of Service / Privacy Policy | Not started | Required before any external users |
| GDPR / data deletion | Not started | User data export and deletion workflows |
| Support system | Not started | Bug reports, feature requests |
| Documentation for end users | Not started | User-facing docs, not just deploy docs |

## 7. Hermes Integration

| What | Status | Notes |
|---|---|---|
| Hermes health check | Not started | `/healthz` covers workbench only. Hermes needs its own liveness probe |
| Hermes restart during active generation | Deferred | Asymmetric restart safety documented in runbook |
| Multi-tenant Hermes profiles | Not started | Separate profile per beta user |

---

## Priority Order for Closed Beta

Rough prioritization of what's needed to go from dogfood → private beta:

1. Multi-user auth (real auth system, not Basic Auth)
2. Tenant isolation verification
3. Object storage for artifacts
4. Automated backups
5. Rate limiting
6. CI/CD pipeline
7. Monitoring / alerting
8. Everything else

---

## Cost Scaling

At $6/mo flat for the dogfood VPS, hosting scales linearly: one VPS per N users.
For 10 beta users: $6/mo (shared VPS). For 50-100 users: consider upgrading to
4-8 GB RAM or splitting services across multiple VPSes.

---

## Decision Log

No decisions deferred. All dogfood-scope decisions are documented in the sprint
plan and execution plan. Future decisions (auth provider, object storage
provider, CI/CD tool) are noted as "Not started" above and will be scoped in
future sprint plans.
