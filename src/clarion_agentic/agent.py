from __future__ import annotations

from pathlib import Path

from agent_framework.azure import AzureAIClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import DefaultAzureCredential

from clarion_agentic.config import Settings
from clarion_agentic.rag.corpus import search_corpus


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.txt"


def get_m365_index_status() -> str:
    settings = Settings.from_env()
    if not settings.corpus_path.exists():
        return (
            "The local Microsoft 365 corpus is missing. Run `python scripts/ingest_m365.py` before asking knowledge questions."
        )

    return f"Local Microsoft 365 corpus is available at {settings.corpus_path}."


def search_m365_corpus(query: str, top_k: int = 5) -> str:
    settings = Settings.from_env()
    results = search_corpus(settings.corpus_path, query, top_k=top_k)
    if not results:
        return (
            "No matching Microsoft 365 records were found in the local corpus. "
            "Refresh the corpus with `python scripts/ingest_m365.py` if the source data may have changed."
        )

    lines = []
    for result in results:
        lines.append(
            "\n".join(
                [
                    f"Source: {result.source}",
                    f"Title: {result.title}",
                    f"Updated: {result.updated_at}",
                    f"URL: {result.url or 'n/a'}",
                    f"Excerpt: {result.text[:1200]}",
                ]
            )
        )
    return "\n\n---\n\n".join(lines)


async def serve_agent(settings: Settings) -> None:
    async with DefaultAzureCredential() as credential:
        async with AzureAIClient(
            project_endpoint=settings.foundry_project_endpoint,
            model_deployment_name=settings.foundry_model_deployment_name,
            credential=credential,
        ).as_agent(
            name=settings.agent_name,
            instructions=PROMPT_PATH.read_text(encoding="utf-8"),
            tools=[search_m365_corpus, get_m365_index_status],
        ) as agent:
            await from_agent_framework(agent).run_async()
