# Clarion Agentic

Clarion Agentic is a Python Microsoft Foundry hosted agent built with Microsoft Agent Framework. It answers over Microsoft 365 content by ingesting Teams channel messages, OneDrive files, and Outlook mail/calendar items through Microsoft Graph, then using a local RAG corpus as a starter implementation.

## What this scaffold includes

- A Microsoft Agent Framework hosted agent exposed through `from_agent_framework`
- Microsoft Graph ingestion code for Teams, OneDrive, Outlook mail, and Outlook calendar
- Local corpus persistence and search for starter RAG behavior
- Foundry deployment assets: `agent.yaml`, `Dockerfile`, `.foundry/agent-metadata.yaml`
- A Teams app manifest template for Microsoft 365 / Teams surface integration
- VS Code launch and task files for local debugging

## Architecture

1. `scripts/ingest_m365.py` pulls content from Microsoft Graph into `data/processed/m365_corpus.jsonl`.
2. The hosted agent uses a search tool to retrieve relevant snippets from that corpus.
3. Foundry hosts the agent over the Responses protocol through the hosting adapter.
4. A Teams app manifest template is included so you can attach the agent to Teams after Azure and Microsoft 365 registration is completed.

## Prerequisites

- Python 3.11+
- Azure CLI logged in, or service principal environment variables configured
- A Microsoft Foundry project with a deployed model
- A Microsoft Entra app registration with Microsoft Graph permissions

Recommended for this repo:

- Reuse your existing Foundry resource `clarion2049`
- Create a dedicated project such as `clarionagentic-dev` for this app
- Keep `clarionagentic-prod` as a separate project for production rollout

Recommended Graph application permissions:

- `Files.Read.All`
- `Mail.Read`
- `Calendars.Read`
- `ChannelMessage.Read.All` or delegated channel access aligned to your tenant policy
- `Team.ReadBasic.All`
- `User.Read.All`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` with your Foundry project endpoint, model deployment, and Microsoft Graph identifiers.

## Ingest Microsoft 365 data

Before ingesting, validate Graph access:

```powershell
python scripts/check_graph_access.py
```

Then ingest:

```powershell
python scripts/ingest_m365.py
```

This creates `data/processed/m365_corpus.jsonl`.

## Run the hosted agent locally

```powershell
python main.py
```

The hosted agent listens on `http://localhost:8088`.

Sample request:

```powershell
$body = @{
    input = "Summarize recent Outlook messages about project status and cite the source."
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

## Web chat UI (browser)

If you prefer a browser chat interface, run:

```powershell
python scripts/web_chat_app.py
```

Then open:

- `https://127.0.0.1:8090`

The UI forwards prompts to the hosted agent endpoint (`http://127.0.0.1:8088/responses`) and shows responses in a chat view.

The script uses a local self-signed certificate for HTTPS and auto-generates `scripts/webchat.crt` and `scripts/webchat.key` if missing.

Partner health status page:

- `https://127.0.0.1:8090/status`
- JSON API: `GET /api/tenant/health`

You can also start it from VS Code tasks with `Run Clarion Web Chat`.

## Deploy to Foundry

This scaffold includes the files Foundry workflows typically need:

- `agent.yaml`
- `Dockerfile`
- `.foundry/agent-metadata.yaml`

You still need to:

1. Build and push the container to Azure Container Registry.
2. Set the environment variables in your hosted agent deployment.
3. Register the Teams app and map the deployed hostname into the manifest template.

## Current Azure Setup

The current live Azure configuration for this repo is:

- Foundry resource: `clarion2049-resource`
- Resource group: `rg-az305`
- Region: `uksouth`
- Dev project: `clarionagentic-dev`
- Dev project endpoint: `https://clarion2049-resource.services.ai.azure.com/api/projects/clarionagentic-dev`
- Current model deployment verified on the resource: `gpt-4o`

Applied governance tags:

- Foundry account: `app=clarion`, `env=shared`, `owner=barrywatson`, `costCenter=agentics`
- Foundry project: `app=clarion`, `env=dev`, `owner=barrywatson`, `costCenter=agentics`

## Related Azure Hardening

During setup, the existing Signalweave Function App in `rg-dev` was checked for overlap risk and hardened for secret handling:

- Function App: `teams-sentiment-func`
- Key Vault created/reused: `kvsignalweavedev2049`
- `AI_LANGUAGE_KEY` was moved from plain app settings storage to a Key Vault reference

Recommended next security step:

- Rotate the underlying AI Language service key and update the Key Vault secret value after rotation

## Teams / Microsoft 365 integration notes

The `teams-app/manifest.template.json` file is intentionally a template. You must replace placeholders for:

- Teams app ID
- Bot or agent application ID
- Hosted domain
- Branding values

## Partner Onboarding

For partner distribution and multi-tenant onboarding, use:

- Checklist: `docs/partner-onboarding-checklist.md`
- Graph preflight: `python scripts/check_graph_access.py`
- Consent verification endpoint: `python scripts/consent_check_server.py`

The consent endpoint is available at `POST /onboarding/consent/check` and accepts:

```json
{
    "access_token": "<jwt-access-token>"
}
```

It returns tenant/app identity claims plus missing Graph scopes/roles to help validate admin consent during onboarding.

Quick demo flow:

```powershell
python scripts/consent_check_server.py
```

In a second terminal:

```powershell
python scripts/test_consent_check.py
```

The test script acquires a Graph token via Azure CLI and posts it to the consent endpoint automatically.

Customer-tenant token flow:

```powershell
python scripts/test_consent_check_with_token.py --token "<tenant-access-token>"
```

Or with a captured callback URL:

```powershell
python scripts/test_consent_check_with_token.py --callback-url "https://yourapp/callback#access_token=..."
```

If no token argument is provided, the script reads `CUSTOMER_ACCESS_TOKEN` from environment variables.

Automatic callback capture flow:

```powershell
python scripts/capture_consent_callback.py
```

This starts a local callback listener (default `http://127.0.0.1:8787/callback`) and automatically submits the captured token to the local consent-check endpoint.

Build onboarding authorize URL from `.env`:

```powershell
python scripts/build_auth_url.py
```

Open browser automatically:

```powershell
python scripts/build_auth_url.py --open
```

Run consolidated onboarding validation:

```powershell
python scripts/validate_partner_onboarding.py
```

With consent token and JSON output:

```powershell
python scripts/validate_partner_onboarding.py --token "<tenant-access-token>" --json
```

## Teams Packaging Helper

Render and package a Teams manifest from template values:

```powershell
python scripts/package_teams_manifest.py \
    --teams-app-id "<teams-app-id>" \
    --bot-app-id "<bot-app-id>" \
    --agent-host-domain "your-agent-host.example.com"
```

This writes:

- `teams-app/dist/manifest.json`
- `teams-app/dist/clarion-teams-app.zip` (if icon files exist)

You can use environment variables instead of arguments: `TEAMS_APP_ID`, `BOT_APP_ID`, `AGENT_HOST_DOMAIN`.

## Teams User Runbook

Use this section to guide partner admins and end users from packaging to daily usage.

### Admin Setup (Partner Or Customer Tenant)

1. Confirm onboarding readiness:

```powershell
python scripts/validate_partner_onboarding.py
```

2. Build the Teams package:

```powershell
python scripts/package_teams_manifest.py \
    --teams-app-id "<teams-app-id>" \
    --bot-app-id "<bot-app-id>" \
    --agent-host-domain "your-agent-host.example.com"
```

3. Verify the package exists:

- `teams-app/dist/clarion-teams-app.zip`

4. Upload the package to Teams:

- Teams admin center: Teams apps > Manage apps > Upload
- Or from Teams client: Apps > Manage your apps > Upload a custom app

5. Assign availability policy:

- Pin for pilot users
- Add to selected teams
- Keep broad rollout disabled until pilot sign-off

### End User Experience In Teams

After installation, users can open the app in:

- Personal scope
- Team scope
- Group chat scope

Typical first-use prompts:

- `What is my m365 status?`
- `Summarize recent Outlook messages about project status.`
- `What changed in Teams channel updates this week?`

Manifest command examples already exposed in Teams:

- `query-m365`
- `refresh-corpus`

### Support Runbook (L1/L2)

1. If users report no responses:

- Check app status page: `https://127.0.0.1:8090/status`
- Check health JSON: `GET /api/tenant/health`

2. If consent or permissions fail:

- Run `python scripts/validate_partner_onboarding.py --json`
- If needed, validate token claims with `scripts/consent_check_server.py`

3. If answers are stale:

- Re-run ingestion: `python scripts/ingest_m365.py`
- Re-test user prompt

4. If Teams package errors occur:

- Re-render manifest with `scripts/package_teams_manifest.py`
- Verify icon files and manifest placeholders were resolved

### Pilot Success Criteria

- 90%+ successful responses for pilot prompt set
- Median response time within expected target for tenant
- No missing critical Graph consent/role requirements
- Tenant health endpoint remains healthy or degraded (not unhealthy)

## Telemetry Schema

Tenant-level telemetry events are documented in:

- `docs/tenant-telemetry-schema.md`

## Important limitations in this starter

- OneDrive ingestion reads text-like files directly and stores metadata for unsupported binary files.
- Teams ingestion assumes you know the team and channel IDs to crawl.
- The RAG implementation is local corpus search, not Azure AI Search or a vector database.

That keeps the project runnable immediately. If you want, the next step is to upgrade the corpus layer to Azure AI Search or Cosmos DB vector indexing.
