import asyncio
import logging

from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from clarion_agentic.config import Settings
from clarion_agentic.graph.client import GraphClient
from clarion_agentic.logging_config import configure_logging
from clarion_agentic.rag.corpus import save_corpus


async def _run() -> None:
    load_dotenv(override=False)
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    async with DefaultAzureCredential() as credential:
        client = GraphClient(settings=settings, credential=credential)
        corpus = await client.fetch_all_documents()
        save_corpus(settings.corpus_path, corpus)
        logging.getLogger(__name__).info("Saved %s corpus documents to %s", len(corpus), settings.corpus_path)


if __name__ == "__main__":
    asyncio.run(_run())
