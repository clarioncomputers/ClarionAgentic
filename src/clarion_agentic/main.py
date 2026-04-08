from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from clarion_agentic.agent import serve_agent
from clarion_agentic.config import Settings
from clarion_agentic.logging_config import configure_logging


async def main() -> None:
    load_dotenv(override=False)
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    await serve_agent(settings)


def run() -> None:
    asyncio.run(main())
