from collections.abc import Iterator
from contextlib import contextmanager

from ..adapters import PydanticAILlmCallRecorder
from ..models import TrackedCaller


class NullLlmCallTracker:
    """No-op `LlmCallTracker`: `BaseAgent`'s default when no tracker is injected.

    Still builds and runs the recorder, so a run without a database keeps the per-call
    `info`/`warning` logs — only the persistence is skipped.
    """

    @contextmanager
    def track(
        self, tracked_caller: TrackedCaller, prompt: str
    ) -> Iterator[PydanticAILlmCallRecorder]:
        """Measures the call and discards the resulting log."""
        with PydanticAILlmCallRecorder(tracked_caller, prompt) as recorder:
            yield recorder
