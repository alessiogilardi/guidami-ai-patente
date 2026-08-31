import pytest

from commons.ai.observability import NullLlmCallTracker, TrackedCaller

_CALLER = TrackedCaller(caller="agent", model="m", system_prompt=None, expects_cost=False)


def test_yields_a_recorder_and_discards_it() -> None:
    tracker = NullLlmCallTracker()

    with tracker.track(_CALLER, "prompt") as recorder:
        pass

    assert recorder.log.caller == "agent"
    assert recorder.log.prompt == "prompt"


def test_does_not_swallow_exceptions() -> None:
    tracker = NullLlmCallTracker()

    with pytest.raises(ValueError, match="boom"), tracker.track(_CALLER, "prompt"):
        raise ValueError("boom")
