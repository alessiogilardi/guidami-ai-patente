"""The tracker's background worker has a container-scoped owner (D5, spec 0013 FR-6)."""

from dataclasses import dataclass, field

from pywire import get_default_container

from commons.ai.observability import NullLlmCallTracker
from guidami_ai_patente.providers import LlmCallTrackerProvider


@dataclass
class _RecordingStack:
    closed: int = 0
    entered: list[object] = field(default_factory=list)

    def enter_context(self, manager: object) -> object:
        self.entered.append(manager)
        return NullLlmCallTracker()

    def close(self) -> None:
        self.closed += 1


def test_the_provider_exposes_a_tracker(api_client: object) -> None:
    provider = get_default_container().resolve(LlmCallTrackerProvider)

    assert hasattr(provider.tracker, "track")


def test_disabled_tracking_yields_the_null_tracker(api_client: object) -> None:
    """The suite's ObservabilityConfig sets enabled=False, so no worker thread starts."""
    provider = get_default_container().resolve(LlmCallTrackerProvider)

    assert isinstance(provider.tracker, NullLlmCallTracker)


def test_the_pre_destroy_hook_closes_the_stack() -> None:
    provider = object.__new__(LlmCallTrackerProvider)
    stack = _RecordingStack()
    provider._stack = stack  # type: ignore[assignment]

    provider.close()

    assert stack.closed == 1
