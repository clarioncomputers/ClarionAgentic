# Teams App Shell

This folder contains a starter Teams manifest template for surfacing the hosted agent in Microsoft Teams.

Before packaging the app, replace every placeholder in `manifest.template.json` and add your Teams icon assets.

Minimum values you must set:

- `TEAMS_APP_ID`
- `BOT_APP_ID`
- `AGENT_HOST_DOMAIN`
- developer metadata

## Build Manifest And Package

From repo root:

```powershell
python scripts/package_teams_manifest.py \
	--teams-app-id "<teams-app-id>" \
	--bot-app-id "<bot-app-id>" \
	--agent-host-domain "your-agent-host.example.com"
```

Outputs:

- `teams-app/dist/manifest.json`
- `teams-app/dist/clarion-teams-app.zip`

The zip command expects `teams-app/color.png` and `teams-app/outline.png`. If you only want the rendered manifest:

```powershell
python scripts/package_teams_manifest.py --no-zip
```

## Deploy And Use In Teams

1. Upload `teams-app/dist/clarion-teams-app.zip` to the Teams admin center.
2. Assign an app setup policy to pilot users/teams.
3. Ask pilot users to start in personal scope first, then team/group chat.
4. Validate first prompt behavior with `What is my m365 status?`.
5. If issues occur, check runtime health via `https://127.0.0.1:8090/status`.
