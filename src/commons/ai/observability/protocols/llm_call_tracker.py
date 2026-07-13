from typing import Protocol

from domain.entities.observability import LlmCallLog


class LlmCallTracker(Protocol):
    """Port for persisting one `LlmCallLog` per `BaseAgent` call.

    Injected into `BaseAgent` as an optional dependency (see
    `docs/plans/2026-07-13--llm-call-tracking.md`, Decision 1). Call sites see
    only this single method (ISP); lifecycle concerns (e.g. flushing pending
    writes on shutdown) live on the concrete implementation, owned by the
    composition root.
    """

    def track(self, log: LlmCallLog) -> None:
        """Records `log`.

        Contractually non-blocking: implementations must not sit on the
        critical path of the LLM call (e.g. by enqueueing the log for a
        background worker rather than persisting synchronously).
        """
        ...
