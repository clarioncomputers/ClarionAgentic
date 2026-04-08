# Partner Onboarding Checklist

Use this checklist when onboarding a new customer tenant to Clarion Agentic.

## 1. App Registration And Identity

- Create a multi-tenant Microsoft Entra app registration for the partner-facing app.
- Configure redirect URIs for your onboarding portal.
- Configure client secret or certificate with a rotation policy.
- Record and store `client_id`, `tenant_id`, and credential references in Key Vault.

## 2. Required Microsoft Graph Permissions

- User.Read.All
- Files.Read.All
- Mail.Read
- Calendars.Read
- ChannelMessage.Read.All

Grant admin consent in the customer tenant before enabling ingestion jobs.

## 3. Tenant Isolation Controls

- Store per-tenant config independently (tenant ID, selected teams/channels, drive IDs).
- Use per-tenant storage/index namespaces.
- Use per-tenant secret references.
- Tag resources for cost attribution (`tenant`, `app`, `env`, `costCenter`).

## 4. Preflight Verification

- Run `python scripts/check_graph_access.py` after loading tenant configuration.
- Run `python scripts/consent_check_server.py` and verify consent claims from onboarding tokens.
- Confirm `teams`, `onedrive`, and `outlook` checks return expected status.

## 5. Operational Readiness

- Enable structured logging with tenant correlation IDs.
- Enable monitoring and alerting for ingestion failures and 403 scope errors.
- Document rollback process for misconfigured consent.

## 6. Compliance Readiness

- Publish privacy statement and data processing details.
- Limit retained content and apply retention policies.
- Document data deletion process per tenant.
