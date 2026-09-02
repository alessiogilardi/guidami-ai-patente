"""Container-managed provider for the LLM call tracker and its worker lifecycle."""

import logging
from contextlib import ExitStack

from pywire import Autowired, pre_destroy, provider

from commons.ai.observability import LlmCallTracker, ObservabilityConfig, build_llm_call_tracker
from guidami_ai_patente.clients import PostgresClientProvider

logger = logging.getLogger(__name__)


@provider
class LlmCallTrackerProvider:
    """Owns the tracker the live judge and the writer record their calls through (D5).

    `build_llm_call_tracker` is a context manager, because a `QueuedLlmCallTracker`
    starts a background worker that must be drained rather than abandoned. Until
    pywire had no teardown mechanism there was no request-independent owner for that
    lifecycle, which is why `labeling.wiring.build_comma_labeler_agent` documents the
    API path as running untracked. pywire 0.6.0's `@pre_destroy` (spec 0013, FR-6)
    removed that obstacle: the manager is entered once here, through an `ExitStack`,
    and closed by `Container.close()` from `pywire_lifespan`'s shutdown.

    **Teardown order is load-bearing.** `Container.close()` runs hooks in reverse
    build order, and this provider is built *after* `PostgresClientProvider` because
    it depends on it — so the queue drains while the pool is still open. Removing that
    dependency edge, or resolving the client some other way, would invert the order and
    lose the tail of the queue on every shutdown.

    With `ObservabilityConfig.enabled` false, `build_llm_call_tracker` yields
    `NullLlmCallTracker`, which still emits the per-call `info` log and persists
    nothing — so disabling tracking is a configuration change, never a code path.
    """

    observability_config: Autowired[ObservabilityConfig]
    postgres: Autowired[PostgresClientProvider]

    def __init__(self) -> None:
        """Enters the tracker's context manager for the lifetime of the container."""
        self._stack = ExitStack()
        self.tracker: LlmCallTracker = self._stack.enter_context(
            build_llm_call_tracker(self.observability_config, self.postgres.client)
        )
        logger.debug("LLM call tracker ready (%s)", type(self.tracker).__name__)

    @pre_destroy
    def close(self) -> None:
        """Drains and releases the tracker. Called once by `Container.close()`."""
        self._stack.close()
