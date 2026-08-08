"""Entry point: loads configuration, builds the FastAPI app, and serves it via uvicorn."""

import logging

import uvicorn

from .api.app import create_app
from .configs import AppConfig

logger = logging.getLogger(__name__)


def main() -> None:
    """Boots the guidami-ai-patente API service."""
    logging.basicConfig(level=logging.INFO)
    config = AppConfig()  # pyright: ignore[reportCallIssue]
    app = create_app(config)
    logger.info("Starting guidami-ai-patente API on %s:%d", config.host, config.port)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
