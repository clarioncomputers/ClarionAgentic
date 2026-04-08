from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def _headers(credential: DefaultAzureCredential) -> dict[str, str]:
    token = await credential.get_token(GRAPH_SCOPE)
    return {
        "Authorization": f"Bearer {token.token}",
        "Accept": "application/json",
    }


async def _check(
    client: httpx.AsyncClient,
    credential: DefaultAzureCredential,
    name: str,
    path: str,
    expected: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    response = await client.get(path, headers=await _headers(credential))
    ok = response.status_code in expected
    return {
        "name": name,
        "status": response.status_code,
        "ok": ok,
        "url": f"{GRAPH_BASE}{path}",
        "error": None if ok else response.text[:500],
    }


def _drive_children_path() -> str:
    drive_id = os.getenv("M365_DRIVE_ID", "").strip()
    drive_path = os.getenv("M365_DRIVE_PATH", "").strip().strip("/")

    if drive_id and drive_path:
        return f"/drives/{drive_id}/root:/{drive_path}:/children?$top=1"
    if drive_id:
        return f"/drives/{drive_id}/root/children?$top=1"
    if drive_path:
        return f"/me/drive/root:/{drive_path}:/children?$top=1"
    return "/me/drive/root/children?$top=1"


async def main() -> None:
    load_dotenv(override=False)

    user_id = os.getenv("M365_USER_ID", "").strip()
    app_client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    app_client_secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()
    is_app_auth = bool(app_client_id and app_client_secret)
    teams_channels = json.loads(os.getenv("M365_TEAMS_CHANNELS", "[]"))

    checks: list[tuple[str, str]] = []
    if is_app_auth:
        if user_id:
            checks.append(("profile", f"/users/{user_id}?$select=id,userPrincipalName"))
        else:
            checks.append(("profile", "/users?$top=1&$select=id,userPrincipalName"))
    else:
        checks.append(("profile", "/me?$select=id,userPrincipalName"))
    if user_id:
        checks.append(("outlook-mail", f"/users/{user_id}/messages?$top=1"))
        checks.append(("outlook-calendar", f"/users/{user_id}/events?$top=1"))

    checks.append(("onedrive", _drive_children_path()))

    if teams_channels:
        first = teams_channels[0]
        checks.append(
            (
                "teams-messages",
                f"/teams/{first['team_id']}/channels/{first['channel_id']}/messages?$top=1",
            )
        )

    async with DefaultAzureCredential() as credential:
        async with httpx.AsyncClient(base_url=GRAPH_BASE, timeout=60.0) as client:
            results = []
            for name, path in checks:
                results.append(await _check(client, credential, name, path))

    print("Graph Access Preflight")
    print("=====================")
    for result in results:
        mark = "OK" if result["ok"] else "FAIL"
        print(f"{mark:4} {result['name']:16} HTTP {result['status']}  {result['url']}")
        if not result["ok"]:
            print(f"      Error: {result['error']}")

    failed = [r for r in results if not r["ok"]]
    if failed:
        print("\nResult: Some Graph checks failed. Fix app permissions/admin consent, then retry.")
        raise SystemExit(1)

    print("\nResult: All configured Graph checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
