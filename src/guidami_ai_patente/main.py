"""Entry point: loads configuration, builds the FastAPI app, and serves it via uvicorn."""

import logging

import uvicorn

from commons.ai.observability import ObservabilityConfig
from commons.configs import OpenRouterConfig
from labeling.configs import LabelingConfig

from .api.app import create_app
from .configs import AppConfig

logger = logging.getLogger(__name__)


def main() -> None:
    """Boots the guidami-ai-patente API service."""
    logging.basicConfig(level=logging.INFO)
    config = AppConfig()  # pyright: ignore[reportCallIssue]
    labeling_config = LabelingConfig()  # pyright: ignore[reportCallIssue]
    open_router_config = OpenRouterConfig()  # pyright: ignore[reportCallIssue]
    observability_config = ObservabilityConfig()
    app = create_app(
        config,
        labeling_config,
        open_router_config=open_router_config,
        observability_config=observability_config,
    )
    logger.info("Starting guidami-ai-patente API on %s:%d", config.host, config.port)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
