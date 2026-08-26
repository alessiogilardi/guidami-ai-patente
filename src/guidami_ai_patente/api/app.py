"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pywire import get_default_container
from pywire.exceptions import RegistrationError
from pywire.fastapi import wire

from guidami_ai_patente.clients import (  # noqa: F401  — imported for pywire registration
    LabelingStackProvider,
    PostgresClientProvider,
)
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.services import JudgeCoherenceChecker

from .exception_handlers import register_exception_handlers
from .routers import health, quiz_images, quiz_questions

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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs the startup diagnostics, then serves.

    The judge-coherence check (FR-14) swallows its own failures, so this never keeps
    the app from starting — see `JudgeCoherenceChecker` for why that is deliberate.
    The check is synchronous SQL, so it crosses to a worker thread like every other
    call into the sync stack (AD-25).
    """
    checker = get_default_container().resolve(JudgeCoherenceChecker)
    await asyncio.to_thread(checker.check)
    yield


def create_app(config: AppConfig) -> FastAPI:
    """Builds and configures the FastAPI application instance.

    Args:
        config: Validated application configuration, built once at the entry point.

    Returns:
        A configured FastAPI application, ready to be served.
    """
    app = FastAPI(title="guidami-ai-patente API", lifespan=_lifespan)
    app.state.config = config
    _register_config(config)
    register_exception_handlers(app)
    wire(app)
    app.include_router(health.router)
    app.include_router(quiz_questions.router)
    app.include_router(quiz_images.router)
    return app
