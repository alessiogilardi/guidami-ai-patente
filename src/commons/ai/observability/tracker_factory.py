from collections.abc import Iterator
from contextlib import contextmanager

from commons.clients import PostgresClient

from .configs import ObservabilityConfig
from .enums import TrackerBackend
from .protocols import LlmCallTracker
from .repositories import PostgresLlmCallLogRepository
from .services import NullLlmCallTracker, QueuedLlmCallTracker


@contextmanager
def build_llm_call_tracker(
    config: ObservabilityConfig, postgres_client: PostgresClient | None
) -> Iterator[LlmCallTracker]:
    """Yields the configured tracker, draining its worker on exit.

    A context manager rather than a plain factory so the worker's lifecycle stays off
    the `LlmCallTracker` port (ISP) while every call site keeps the same
    `with ... as tracker` shape.

    Falls back to `NullLlmCallTracker` when tracking is disabled or when no DB client
    could be opened: observability is never a reason to abort a run.

    Args:
        config: Tracking settings — whether tracking is on, which backend, which table.
        postgres_client: Open client for the tracking DB, or `None` when unavailable.
    """
    if not config.enabled or postgres_client is None:
        yield NullLlmCallTracker()
        return

    match config.backend:
        case TrackerBackend.POSTGRES:
            repository = PostgresLlmCallLogRepository(config.table, postgres_client)

    with QueuedLlmCallTracker(config.queue_join_timeout_s, repository) as tracker:
        yield tracker
