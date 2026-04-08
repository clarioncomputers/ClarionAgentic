from __future__ import annotations

import asyncio
import logging
import socket

from dotenv import load_dotenv

from clarion_agentic.agent import serve_agent
from clarion_agentic.config import Settings
from clarion_agentic.logging_config import configure_logging


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


async def main() -> None:
    load_dotenv(override=False)
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if _is_port_in_use("127.0.0.1", 8088):
        logging.getLogger(__name__).warning(
            "Hosted agent already appears to be running on http://127.0.0.1:8088. "
            "Stop the existing process before starting a new one."
        )
        return

    await serve_agent(settings)


def run() -> None:
    asyncio.run(main())
