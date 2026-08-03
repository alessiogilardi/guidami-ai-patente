from typing import Protocol

from .item_progress_reporter import ItemProgressReporter


class ProgressReporter(ItemProgressReporter, Protocol):
    """Port for reporting flow/step/item progress of a monitored CLI run.

    Extends `ItemProgressReporter` with the flow- and step-level lifecycle, so a
    single object can be handed to a flow factory (AD-4) and still be structurally
    compatible with the narrower port the instrumented services depend on.
    """

    def begin_run(self, total_flows: int) -> None:
        """Starts a run consisting of `total_flows` flows.

        Args:
            total_flows: Total number of flows the invocation will run.
        """
        ...

    def begin_flow(self, name: str) -> None:
        """Marks the start of one flow within the run.

        Args:
            name: The flow's name (its `FlowBuilder` name).
        """
        ...

    def end_flow(self) -> None:
        """Marks the completion of the current flow."""
        ...

    def begin_step(self, name: str, index: int, total: int) -> None:
        """Marks the start of one step within the current flow.

        Args:
            name: The step's name.
            index: 1-based position of the step within the flow, matching
                `FlowProgress.index`.
            total: Total number of steps in the flow.
        """
        ...

    def end_step(self) -> None:
        """Marks the completion of the current step.

        Implementations must close any open item track before advancing the step.
        """
        ...
