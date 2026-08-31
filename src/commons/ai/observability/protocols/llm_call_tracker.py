from contextlib import AbstractContextManager
from typing import Protocol

from ..adapters import PydanticAILlmCallRecorder
from ..models import TrackedCaller


class LlmCallTracker(Protocol):
    """Port `BaseAgent` uses to record one call.

    Injected into `BaseAgent` as an optional dependency; `None` is normalized to
    `NullLlmCallTracker`, so the tracked code path is always the same one.

    Call sites see a single method (ISP). Lifecycle concerns — starting and draining a
    background worker — live on the concrete implementation and are owned by the
    composition root through `build_llm_call_tracker`.
    """

    def track(
        self, tracked_caller: TrackedCaller, prompt: str
    ) -> AbstractContextManager[PydanticAILlmCallRecorder]:
        """Measures one call and records it on exit.

        The returned context manager yields the recorder: pass the `AgentRunResult` to
        `recorder.record(...)` inside the block. Implementations must record the call on
        the failure path too, and must never swallow the block's exception.
        """
        ...
