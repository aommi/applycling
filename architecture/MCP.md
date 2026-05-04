# MCP (Model Context Protocol) — applycling

## Compatibility Discipline

When a new pipeline capability ships, the corresponding MCP tool must ship
in the same PR. This is enforced via:
- `memory/semantic.md` Key Patterns — active-session reminder
- `.agent/project.yaml` conventions — propagates to all agent entry files

Pipeline and MCP surface must not drift. Any change to the pipeline's public
contract (new argument, new return field, new step, new capability like
`interview_prep`) requires a corresponding MCP tool update in the same
changeset.

### MCP v1 Surface

| Tool | Status | Ticket |
|------|--------|--------|
| `add_job` | ✅ Shipped | MCP-T1 |
| `list_jobs` | ✅ Shipped | MCP-T2 |
| `get_package` | ✅ Shipped | MCP-T2 |
| `update_job_status` | 📋 Deferred | MCP-T3 |
| `interview_prep` | 📋 Deferred | MCP-T3 |
| `refine_package` | 📋 Deferred | MCP-T3 |
