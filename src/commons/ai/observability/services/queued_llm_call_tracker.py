import logging
import queue
import threading
from types import TracebackType

from ..entities import LlmCallLogEntity
from ..protocols import LlmCallLogRepository

logger = logging.getLogger(__name__)


class _Shutdown:
    """Sentinel enqueued by `close()` to stop the worker loop."""


_SHUTDOWN = _Shutdown()


class QueuedLlmCallTracker:
    """`LlmCallTracker` persisting logs from a background daemon worker thread.

    `track()` is a `queue.SimpleQueue.put` (microseconds, thread-safe), so it serves
    both `BaseAgent.run` and `run_sync` without touching the event loop. The worker
    drains the queue sequentially, calling `repository.insert` for each log. A failing
    `insert` is logged and swallowed (see plan Decision 4) — observability must never
    break the main flow. Use as a context manager, or call `close()` directly.
    """

    def __init__(self, join_timeout_s: float, repository: LlmCallLogRepository) -> None:
        """Stores the shutdown join timeout and the repository used by the worker thread."""
        self._join_timeout_s = join_timeout_s
        self._repository = repository
        self._queue: queue.SimpleQueue[LlmCallLogEntity | _Shutdown] = queue.SimpleQueue()
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

    def track(self, log: LlmCallLogEntity) -> None:
        """Enqueues `log` for the worker thread; returns immediately."""
        self._queue.put(log)

    def close(self) -> None:
        """Enqueues the shutdown sentinel and joins the worker, bounded by `join_timeout_s`."""
        self._queue.put(_SHUTDOWN)
        if self._worker is None:
            return

        self._worker.join(timeout=self._join_timeout_s)
        if self._worker.is_alive():
            logger.warning("QueuedLlmCallTracker worker did not shut down within timeout")

    def _drain(self) -> None:
        """Worker loop: persists queued logs until the shutdown sentinel is received."""
        while True:
            item = self._queue.get()
            if isinstance(item, _Shutdown):
                return
            self._persist(item)

    def _persist(self, log: LlmCallLogEntity) -> None:
        """Inserts the log; swallows and logs any failure."""
        try:
            self._repository.insert(log)
        except Exception:
            logger.warning("failed to persist LLM call log", exc_info=True)
