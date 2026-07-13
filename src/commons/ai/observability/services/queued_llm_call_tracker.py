import logging
import queue
import threading
from types import TracebackType

from domain.entities.observability import LlmCallLog

from .protocols.cost_calculator import _CostCalculator
from .protocols.llm_call_log_repository import _LlmCallLogRepository

logger = logging.getLogger(__name__)

# Not a ctor param: nobody asked for it, and a configurable knob would force
# plain-data-with-default before required dependencies (see plan Decision 3).
_JOIN_TIMEOUT_S = 10.0


class _Shutdown:
    """Sentinel enqueued by `close()` to stop the worker loop."""


_SHUTDOWN = _Shutdown()


class QueuedLlmCallTracker:
    """`LlmCallTracker` persisting logs from a background daemon worker thread.

    `track()` is a `queue.SimpleQueue.put` (microseconds, thread-safe), so it serves
    both `BaseAgent.run` and `run_sync` without touching the event loop. The worker
    drains the queue sequentially: cost lookup, then `repository.insert`. A failing
    `insert` is logged and swallowed (see plan Decision 4) — observability must never
    break the main flow. Use as a context manager, or call `close()` directly.
    """

    def __init__(
        self, repository: _LlmCallLogRepository, cost_calculator: _CostCalculator
    ) -> None:
        """Stores the repository and cost calculator used by the worker thread."""
        self._repository = repository
        self._cost_calculator = cost_calculator
        self._queue: queue.SimpleQueue[LlmCallLog | _Shutdown] = queue.SimpleQueue()
        self._worker: threading.Thread | None = None

    def __enter__(self) -> "QueuedLlmCallTracker":
        """Starts the daemon worker thread."""
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Flushes pending logs (see `close`)."""
        self.close()

    def track(self, log: LlmCallLog) -> None:
        """Enqueues `log` for the worker thread; returns immediately."""
        self._queue.put(log)

    def close(self) -> None:
        """Enqueues the shutdown sentinel and joins the worker, bounded by `_JOIN_TIMEOUT_S`."""
        self._queue.put(_SHUTDOWN)
        if self._worker is None:
            return

        self._worker.join(timeout=_JOIN_TIMEOUT_S)
        if self._worker.is_alive():
            logger.warning("QueuedLlmCallTracker worker did not shut down within timeout")

    def _drain(self) -> None:
        """Worker loop: persists queued logs until the shutdown sentinel is received."""
        while True:
            item = self._queue.get()
            if isinstance(item, _Shutdown):
                return
            self._persist(item)

    def _persist(self, log: LlmCallLog) -> None:
        """Computes `cost_usd` and inserts the log; swallows and logs any failure."""
        try:
            cost = self._cost_calculator.cost_usd(log.model, log.input_tokens, log.output_tokens)
            self._repository.insert(log.model_copy(update={"cost_usd": cost}))
        except Exception:
            logger.warning("failed to persist LLM call log", exc_info=True)
