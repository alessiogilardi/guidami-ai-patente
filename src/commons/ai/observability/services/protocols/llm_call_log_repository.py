from typing import Protocol

from domain.entities.observability import LlmCallLogEntity


class _LlmCallLogRepository(Protocol):
    """Structural contract for `QueuedLlmCallTracker`'s repository dependency.

    Private: not a cross-package port like `LlmCallTracker`. It exists only so
    `QueuedLlmCallTracker` depends on an abstraction rather than the concrete
    `LlmCallLogRepository`, keeping it testable with duck-typed fakes.
    """

    def insert(self, log: LlmCallLogEntity) -> None: ...
