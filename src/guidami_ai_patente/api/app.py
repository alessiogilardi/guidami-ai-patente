"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from pywire import get_default_container
from pywire.exceptions import RegistrationError
from pywire.fastapi import wire

from guidami_ai_patente.configs import AppConfig

from .routers import health

logger = logging.getLogger(__name__)


def _register_config(config: AppConfig) -> None:
    """Registers `config` as the container's single `AppConfig` instance.

    pywire refuses to displace an existing registration, which is what makes the
    "one AppConfig per process" rule mechanical rather than conventional. Rebuilding
    the app with the *same* object (a reload, a second `create_app` in a script) is
    therefore tolerated; rebuilding it with a *different* one raises, because every
    already-resolved component would keep pointing at the first — silently, and
    possibly at another database.
    """
    container = get_default_container()
    try:
        container.register_instance(config, as_type=AppConfig)
    except RegistrationError:
        if container.resolve(AppConfig) is not config:
            raise


def create_app(config: AppConfig) -> FastAPI:
    """Builds and configures the FastAPI application instance.

    Args:
        config: Validated application configuration, built once at the entry point.

    Returns:
        A configured FastAPI application, ready to be served.
    """
    app = FastAPI(title="guidami-ai-patente API")
    app.state.config = config
    _register_config(config)
    wire(app)
    app.include_router(health.router)
    return app
