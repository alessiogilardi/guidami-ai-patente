class NullProgressReporter:
    """No-op `ProgressReporter`: the default collaborator when no reporter is injected.

    Lets flow factories and instrumented services always go through the tracked code
    path without branching on whether a reporter was provided (AD-3).
    """

    def begin_run(self, total_flows: int) -> None:
        """Discards the call; no observable side effect."""

    def begin_flow(self, name: str) -> None:
        """Discards the call; no observable side effect."""

    def end_flow(self) -> None:
        """Discards the call; no observable side effect."""

    def begin_step(self, name: str, index: int, total: int) -> None:
        """Discards the call; no observable side effect."""

    def end_step(self) -> None:
        """Discards the call; no observable side effect."""

    def begin_items(self, label: str, total: int) -> None:
        """Discards the call; no observable side effect."""

    def advance_item(self) -> None:
        """Discards the call; no observable side effect."""

    def end_items(self) -> None:
        """Discards the call; no observable side effect."""
