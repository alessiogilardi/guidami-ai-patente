"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pywire import get_default_container
from pywire.exceptions import RegistrationError
from pywire.fastapi import pywire_lifespan

from commons.ai.observability import ObservabilityConfig
from commons.configs import OpenRouterConfig
from guidami_ai_patente.agents import (  # noqa: F401  — imported for pywire registration
    ExplanationWriterAgent,
)
from guidami_ai_patente.clients import (  # noqa: F401  — imported for pywire registration
    PostgresClientProvider,
)
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.providers import (  # noqa: F401  — imported for pywire registration
    LabelingStackProvider,
    LiveLabelingStackProvider,
    LlmCallTrackerProvider,
    OpenRouterProviderComponent,
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


async def _run_judge_coherence_check() -> None:
    """Resolves and runs `JudgeCoherenceChecker`; never raises (FR-14).

    `check()` swallows its own failures, so this never keeps the app from starting —
    see `JudgeCoherenceChecker` for why that is deliberate. The check is synchronous
    SQL, so it crosses to a worker thread like every other call into the sync stack
    (AD-25).

    `resolve()` itself is not covered by that guard: building `JudgeCoherenceChecker`
    transitively constructs `GoldenSetReadRepository` -> `PostgresClientProvider`,
    whose `__init__` opens a connection pool eagerly with `wait=True` and raises
    `psycopg_pool.PoolTimeout` if Postgres isn't reachable yet. Startup must survive
    that too, so resolution gets the same "diagnostic must never abort startup"
    treatment as the check's own body.

    Kept as its own top-level function, rather than inlined in `_lifespan`, so a test
    can exercise the resolve-can-also-raise guard directly without going through
    `pywire_lifespan` — entering that would bind/close the real process-wide default
    container, tearing down beans other tests in the same session may still hold.
    """
    try:
        checker = get_default_container().resolve(JudgeCoherenceChecker)
    except Exception:  # noqa: BLE001 — a diagnostic must not abort startup (FR-14)
        logger.warning("Judge coherence checker could not be built; continuing", exc_info=True)
    else:
        await asyncio.to_thread(checker.check)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Binds the default container to the app, runs startup diagnostics, then serves.

    `pywire_lifespan` is the only way to configure a container on a FastAPI app: the
    older `wire()` was deprecated in pywire 0.7.0 and removed in 0.8.0. It is nested on
    the outside per its documented composition pattern: it binds `app.state.
    pywire_container` before our own startup code below runs, and its own teardown —
    `Container.close()`, running every resolved bean's `@pre_destroy` hook, today only
    `PostgresClientProvider`'s pool — sits in a `finally`, so it only fires after our
    `yield` returns control, i.e. after our own shutdown, none of which we have here.

    Shutdown teardown (spec 0013, FR-6) is `pywire_lifespan`'s own; a teardown failure
    is allowed to propagate and be logged by uvicorn: nothing downstream depends on the
    process surviving it.
    """
    async with pywire_lifespan(app):
        await _run_judge_coherence_check()
        yield


def create_app(
    config: AppConfig,
    labeling_config: LabelingConfig,
    *,
    open_router_config: OpenRouterConfig,
    observability_config: ObservabilityConfig,
) -> FastAPI:
    """Builds and configures the FastAPI application instance.

    Args:
        config: Validated application configuration, built once at the entry point.
        labeling_config: The shared judge/run configuration (spec 0013, FR-1), loaded
            independently of `config` from the same `configs/labeling.yaml` the
            ingestor reads.
        open_router_config: The model credentials, a root settings class of its own
            rather than a nested field — same reasoning as `labeling_config`.
        observability_config: LLM call tracking settings (D5), likewise a root.

    Returns:
        A configured FastAPI application, ready to be served.
    """
    app = FastAPI(title="guidami-ai-patente API", lifespan=_lifespan)
    app.state.config = config
    _register_instance(config, AppConfig)
    _register_instance(labeling_config, LabelingConfig)
    _register_instance(open_router_config, OpenRouterConfig)
    _register_instance(observability_config, ObservabilityConfig)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(quiz_questions.router)
    app.include_router(quiz_images.router)
    return app
