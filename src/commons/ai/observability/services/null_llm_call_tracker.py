from ..entities import LlmCallLogEntity


class NullLlmCallTracker:
    """No-op `LlmCallTracker`: `BaseAgent`'s default collaborator when no tracker is injected.

    Lets `BaseAgent.run`/`run_sync` always go through the tracked code path without
    branching on whether a tracker was provided.
    """

    def track(self, log: LlmCallLogEntity) -> None:
        """Discards `log`; no observable side effect."""
