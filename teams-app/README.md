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
