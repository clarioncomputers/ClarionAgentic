from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = ROOT_DIR / "data" / "processed" / "m365_corpus.jsonl"


@dataclass(slots=True)
class TeamsChannelTarget:
    team_id: str
    channel_id: str
    label: str = ""


@dataclass(slots=True)
class Settings:
    foundry_project_endpoint: str
    foundry_model_deployment_name: str
    agent_name: str = "clarion-m365-rag"
    log_level: str = "INFO"
    m365_user_id: str = ""
    m365_drive_id: str = ""
    m365_drive_path: str = ""
    m365_max_items: int = 25
    teams_channels: list[TeamsChannelTarget] = field(default_factory=list)
    corpus_path: Path = field(default_factory=lambda: DEFAULT_CORPUS_PATH)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_channels = os.getenv("M365_TEAMS_CHANNELS", "[]")
        channel_values = json.loads(raw_channels)
        channels = [
            TeamsChannelTarget(
                team_id=item["team_id"],
                channel_id=item["channel_id"],
                label=item.get("label", ""),
            )
            for item in channel_values
        ]

        return cls(
            foundry_project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT", ""),
            foundry_model_deployment_name=os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")
            or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", ""),
            agent_name=os.getenv("AGENT_NAME", "clarion-m365-rag"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            m365_user_id=os.getenv("M365_USER_ID", ""),
            m365_drive_id=os.getenv("M365_DRIVE_ID", ""),
            m365_drive_path=os.getenv("M365_DRIVE_PATH", ""),
            m365_max_items=int(os.getenv("M365_MAX_ITEMS", "25")),
            teams_channels=channels,
        )
