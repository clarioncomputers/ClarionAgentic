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

## Important limitations in this starter

- OneDrive ingestion reads text-like files directly and stores metadata for unsupported binary files.
- Teams ingestion assumes you know the team and channel IDs to crawl.
- The RAG implementation is local corpus search, not Azure AI Search or a vector database.

That keeps the project runnable immediately. If you want, the next step is to upgrade the corpus layer to Azure AI Search or Cosmos DB vector indexing.
