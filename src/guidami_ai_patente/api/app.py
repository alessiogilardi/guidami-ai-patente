"""FastAPI application factory."""

from fastapi import FastAPI
from pywire.fastapi import wire

from guidami_ai_patente.configs import AppConfig

from .routers import health


def create_app(config: AppConfig) -> FastAPI:
    """Builds and configures the FastAPI application instance.

    Args:
        config: Validated application configuration, built once at the entry point.

    Returns:
        A configured FastAPI application, ready to be served.
    """
    app = FastAPI(title="guidami-ai-patente API")
    app.state.config = config
    wire(app)
    app.include_router(health.router)
    return app
