from domain.entities.observability import LlmCallLog


class NullLlmCallTracker:
    """No-op `LlmCallTracker`: `BaseAgent`'s default collaborator when no tracker is injected.

    Lets `BaseAgent.run`/`run_sync` always go through the tracked code path without
    branching on whether a tracker was provided.
    """

    def track(self, log: LlmCallLog) -> None:
        """Discards `log`; no observable side effect."""
