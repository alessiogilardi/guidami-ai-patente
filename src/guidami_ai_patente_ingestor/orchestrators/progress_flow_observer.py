from flowstep import Step
from flowstep.core.observability.models import FlowProgress

from commons.observability import ProgressReporter


class ProgressFlowObserver:
    """Adapts flowstep's step-lifecycle hooks onto a `ProgressReporter`.

    Registered via `FlowBuilder.add_observer` (AD-4): step/flow progress rides
    `flowstep`'s existing `FlowObserver` protocol, satisfied here structurally
    (`FlowObserver` is a `Protocol`, so this class does not subclass it).
    """

    def __init__(self, progress: ProgressReporter) -> None:
        """Injects the reporter driven by this observer's lifecycle hooks."""
        self._progress = progress

    def on_start(self, step: Step, progress: FlowProgress) -> None:
        """Reports the step's position as it starts."""
        self._progress.begin_step(step.name, progress.index, progress.total)

    def on_end(self, step: Step, duration_ms: float, progress: FlowProgress) -> None:
        """Reports the step's completion. `duration_ms` and `progress` are unused."""
        self._progress.end_step()

    def on_error(self, step: Step, error: Exception, progress: FlowProgress) -> None:
        """Reports the step's completion even on failure, so no bar is left dangling."""
        self._progress.end_step()
