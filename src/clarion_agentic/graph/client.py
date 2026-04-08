from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential

from clarion_agentic.config import Settings, TeamsChannelTarget
from clarion_agentic.rag.corpus import CorpusDocument


LOGGER = logging.getLogger(__name__)
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TAG_PATTERN = re.compile(r"<[^>]+>")


class GraphClient:
    def __init__(self, settings: Settings, credential: DefaultAzureCredential) -> None:
        self._settings = settings
        self._credential = credential

    async def _headers(self) -> dict[str, str]:
        token = await self._credential.get_token(GRAPH_SCOPE)
        return {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/json",
        }

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=GRAPH_BASE_URL, timeout=60.0) as client:
            response = await client.get(path, headers=await self._headers(), params=params)
            response.raise_for_status()
            return response.json()

    async def _get_text(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url, headers=await self._headers())
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text" in content_type or "json" in content_type or "xml" in content_type:
                return response.text[:10000]
            return "Binary file content was skipped during ingestion."

    async def fetch_all_documents(self) -> list[CorpusDocument]:
        documents: list[CorpusDocument] = []
        documents.extend(await self._safe_fetch("outlook-mail", self.fetch_outlook_messages))
        documents.extend(await self._safe_fetch("outlook-calendar", self.fetch_outlook_events))
        documents.extend(await self._safe_fetch("onedrive", self.fetch_onedrive_documents))
        documents.extend(await self._safe_fetch("teams", self.fetch_teams_messages))
        return documents

    async def _safe_fetch(self, source_name: str, fetch_fn: Any) -> list[CorpusDocument]:
        try:
            return await fetch_fn()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                LOGGER.warning(
                    "Skipping source %s due to permission/auth issue (%s): %s",
                    source_name,
                    status,
                    exc,
                )
                return []
            raise

    async def fetch_outlook_messages(self) -> list[CorpusDocument]:
        if not self._settings.m365_user_id:
            return []

        data = await self._get_json(
            f"/users/{self._settings.m365_user_id}/messages",
            params={
                "$top": self._settings.m365_max_items,
                "$select": "id,subject,bodyPreview,webLink,receivedDateTime,from",
                "$orderby": "receivedDateTime desc",
            },
        )
        return [
            CorpusDocument(
                doc_id=f"outlook-message:{item['id']}",
                source="outlook-mail",
                title=item.get("subject") or "Untitled message",
                url=item.get("webLink", ""),
                text=item.get("bodyPreview", ""),
                updated_at=item.get("receivedDateTime", ""),
                metadata={"from": item.get("from", {})},
            )
            for item in data.get("value", [])
        ]

    async def fetch_outlook_events(self) -> list[CorpusDocument]:
        if not self._settings.m365_user_id:
            return []

        data = await self._get_json(
            f"/users/{self._settings.m365_user_id}/events",
            params={
                "$top": self._settings.m365_max_items,
                "$select": "id,subject,bodyPreview,webLink,start,end,lastModifiedDateTime,location",
                "$orderby": "lastModifiedDateTime desc",
            },
        )
        return [
            CorpusDocument(
                doc_id=f"outlook-event:{item['id']}",
                source="outlook-calendar",
                title=item.get("subject") or "Untitled event",
                url=item.get("webLink", ""),
                text=item.get("bodyPreview", ""),
                updated_at=item.get("lastModifiedDateTime", ""),
                metadata={
                    "start": item.get("start", {}),
                    "end": item.get("end", {}),
                    "location": item.get("location", {}),
                },
            )
            for item in data.get("value", [])
        ]

    async def fetch_onedrive_documents(self) -> list[CorpusDocument]:
        path = self._resolve_drive_children_path()
        data = await self._get_json(path, params={"$top": self._settings.m365_max_items})
        documents: list[CorpusDocument] = []

        for item in data.get("value", []):
            if item.get("folder"):
                continue

            text = item.get("description", "")
            if item.get("file"):
                try:
                    text = await self._get_text(f"{GRAPH_BASE_URL}/drives/{item['parentReference']['driveId']}/items/{item['id']}/content")
                except httpx.HTTPError as exc:
                    LOGGER.warning("Could not read OneDrive file %s: %s", item.get("name"), exc)
                    text = f"File metadata only. Name: {item.get('name', 'unknown')}"

            documents.append(
                CorpusDocument(
                    doc_id=f"onedrive:{item['id']}",
                    source="onedrive",
                    title=item.get("name") or "Untitled file",
                    url=item.get("webUrl", ""),
                    text=text,
                    updated_at=item.get("lastModifiedDateTime", ""),
                    metadata={"size": item.get("size", 0)},
                )
            )

        return documents

    async def fetch_teams_messages(self) -> list[CorpusDocument]:
        documents: list[CorpusDocument] = []
        for channel in self._settings.teams_channels:
            documents.extend(await self._fetch_channel_messages(channel))
        return documents

    async def _fetch_channel_messages(self, channel: TeamsChannelTarget) -> list[CorpusDocument]:
        data = await self._get_json(
            f"/teams/{channel.team_id}/channels/{channel.channel_id}/messages",
            params={"$top": self._settings.m365_max_items},
        )
        documents: list[CorpusDocument] = []
        for item in data.get("value", []):
            html_body = item.get("body", {}).get("content", "")
            clean_body = TAG_PATTERN.sub(" ", html_body)
            author = item.get("from", {}).get("user", {}).get("displayName", "Unknown")
            documents.append(
                CorpusDocument(
                    doc_id=f"teams-message:{item['id']}",
                    source="teams",
                    title=f"{channel.label or channel.channel_id} - {author}",
                    url=item.get("webUrl", ""),
                    text=clean_body.strip(),
                    updated_at=item.get("lastModifiedDateTime", item.get("createdDateTime", "")),
                    metadata={
                        "team_id": channel.team_id,
                        "channel_id": channel.channel_id,
                        "author": author,
                    },
                )
            )
        return documents

    def _resolve_drive_children_path(self) -> str:
        if self._settings.m365_drive_id and self._settings.m365_drive_path:
            return f"/drives/{self._settings.m365_drive_id}/root:/{self._settings.m365_drive_path}:/children"
        if self._settings.m365_drive_id:
            return f"/drives/{self._settings.m365_drive_id}/root/children"
        if self._settings.m365_drive_path:
            return f"/me/drive/root:/{self._settings.m365_drive_path}:/children"
        return "/me/drive/root/children"
