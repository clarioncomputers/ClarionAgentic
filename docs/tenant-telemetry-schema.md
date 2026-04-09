# Tenant Telemetry Schema

Clarion web chat emits structured tenant-level telemetry entries to application logs using JSON payloads.

## Event: chat_request

- `event`: `chat_request`
- `timestamp_utc`: UTC timestamp
- `tenant_id`: tenant correlation from `x-tenant-id` header (or `unknown`)
- `outcome`: `ok`, `http_error`, or `connect_error`
- `latency_ms`: request duration in milliseconds
- `prompt_chars`: input prompt character count
- `status_code`: optional HTTP status when available

## Event: tenant_health_checked

- `event`: `tenant_health_checked`
- `timestamp_utc`: UTC timestamp
- `tenant_id`: tenant correlation from `x-tenant-id` header (or `unknown`)
- `overall_status`: `healthy`, `degraded`, or `unhealthy`

## Consumption Notes

- Emit logs to your central sink (App Insights, Log Analytics, SIEM).
- Use `tenant_id` plus `event` for per-tenant dashboards.
- Keep tenant IDs pseudonymous if required by policy.
