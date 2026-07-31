from typing import Protocol


class ItemProgressReporter(Protocol):
    """Port for reporting per-item progress within a long-running unit of work.

    Narrower than `ProgressReporter` (ISP): call sites that only tick through a
    batch of items (e.g. `EmbeddingService`, `ContextEnricher`) depend on this
    protocol alone, never on the flow/step-level methods they never call.

    Contract: `begin_items` replaces any currently open item track (no explicit
    close is required before starting a new one). `advance_item` and `end_items`
    must be no-ops, never raise, when called with no track open.
    """

    def begin_items(self, label: str, total: int) -> None:
        """Opens a new item track, replacing any track already open.

        Args:
            label: Short description of the items being tracked (e.g. "batches").
            total: Total number of items expected in this track.
        """
        ...

    def advance_item(self) -> None:
        """Advances the currently open item track by one. No-op if none is open."""
        ...

    def end_items(self) -> None:
        """Closes the currently open item track. No-op if none is open."""
        ...
