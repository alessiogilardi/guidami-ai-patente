from commons.ai.observability import (
    NullLlmCallTracker,
    ObservabilityConfig,
    QueuedLlmCallTracker,
    build_llm_call_tracker,
)


class _FakeClient:
    """Stands in for PostgresClient; the factory only passes it to the repository."""

    def execute(self, query: object, params: object = None) -> None:
        pass


def test_yields_null_tracker_when_disabled() -> None:
    config = ObservabilityConfig(enabled=False)

    with build_llm_call_tracker(config, _FakeClient()) as tracker:  # pyright: ignore[reportArgumentType]
        assert isinstance(tracker, NullLlmCallTracker)


def test_yields_null_tracker_without_a_client() -> None:
    config = ObservabilityConfig(enabled=True)

    with build_llm_call_tracker(config, None) as tracker:
        assert isinstance(tracker, NullLlmCallTracker)


def test_yields_queued_tracker_when_enabled_with_a_client() -> None:
    config = ObservabilityConfig(enabled=True)

    with build_llm_call_tracker(config, _FakeClient()) as tracker:  # pyright: ignore[reportArgumentType]
        assert isinstance(tracker, QueuedLlmCallTracker)


def test_closes_the_queued_tracker_on_exit() -> None:
    config = ObservabilityConfig(enabled=True)

    with build_llm_call_tracker(config, _FakeClient()) as tracker:  # pyright: ignore[reportArgumentType]
        captured = tracker

    assert isinstance(captured, QueuedLlmCallTracker)
    assert captured._worker is not None and not captured._worker.is_alive()  # noqa: SLF001
