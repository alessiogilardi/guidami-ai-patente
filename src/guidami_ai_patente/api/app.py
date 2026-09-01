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
    PostgresClientProvider,
)
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.providers import (  # noqa: F401  — imported for pywire registration
    LabelingStackProvider,
)
from guidami_ai_patente.services import JudgeCoherenceChecker
from labeling.configs import LabelingConfig

from .exception_handlers import register_exception_handlers
from .routers import health, quiz_images, quiz_questions

logger = logging.getLogger(__name__)


def _register_instance[T](instance: T, as_type: type[T]) -> None:
    """Registers `instance` as the container's single `as_type` instance.

    pywire refuses to displace an existing registration, which is what makes the
    "one instance per process" rule mechanical rather than conventional. Rebuilding
    the app with the *same* object (a reload, a second `create_app` in a script) is
    therefore tolerated; rebuilding it with a *different* one raises, because every
    already-resolved component would keep pointing at the first — silently, and
    possibly at another database or a different judge epoch (spec 0013, FR-1).
    """
    container = get_default_container()
    try:
        container.register_instance(instance, as_type=as_type)
    except RegistrationError:
        if container.resolve(as_type) is not instance:
            raise


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs the startup diagnostics, then serves; closes the container on shutdown.

    The judge-coherence check (FR-14) swallows its own failures, so this never keeps
    the app from starting — see `JudgeCoherenceChecker` for why that is deliberate.
    The check is synchronous SQL, so it crosses to a worker thread like every other
    call into the sync stack (AD-25).

    `resolve()` itself is not covered by that guard: building `JudgeCoherenceChecker`
    transitively constructs `GoldenSetReadRepository` -> `PostgresClientProvider`,
    whose `__init__` opens a connection pool eagerly with `wait=True` and raises
    `psycopg_pool.PoolTimeout` if Postgres isn't reachable yet. Startup must survive
    that too, so resolution gets the same "diagnostic must never abort startup"
    treatment as the check's own body.

    Shutdown (spec 0013, FR-6) closes the default container, which runs every
    resolved bean's `@pre_destroy` hook — today only `PostgresClientProvider`'s pool.
    Unlike the startup diagnostic, a shutdown teardown failure is allowed to
    propagate and be logged by uvicorn: nothing downstream depends on the process
    surviving it.
    """
    try:
        checker = get_default_container().resolve(JudgeCoherenceChecker)
    except Exception:  # noqa: BLE001 — a diagnostic must not abort startup (FR-14)
        logger.warning("Judge coherence checker could not be built; continuing", exc_info=True)
    else:
        await asyncio.to_thread(checker.check)
    try:
        yield
    finally:
        await asyncio.to_thread(get_default_container().close)


def create_app(config: AppConfig, labeling_config: LabelingConfig) -> FastAPI:
    """Builds and configures the FastAPI application instance.

    Args:
        config: Validated application configuration, built once at the entry point.
        labeling_config: The shared judge/run configuration (spec 0013, FR-1), loaded
            independently of `config` from the same `configs/labeling.yaml` the
            ingestor reads.

    Returns:
        A configured FastAPI application, ready to be served.
    """
    app = FastAPI(title="guidami-ai-patente API", lifespan=_lifespan)
    app.state.config = config
    _register_instance(config, AppConfig)
    _register_instance(labeling_config, LabelingConfig)
    register_exception_handlers(app)
    wire(app)
    app.include_router(health.router)
    app.include_router(quiz_questions.router)
    app.include_router(quiz_images.router)
    return app
