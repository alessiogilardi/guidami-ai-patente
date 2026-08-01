import logging
import threading
import time
from decimal import Decimal

import pytest

from commons.ai.observability import QueuedLlmCallTracker
from domain.entities.observability import LlmCallLogEntity


class _FakeRepository:
    """Collects inserted logs in memory, in insertion order."""

    def __init__(self) -> None:
        self.inserted: list[LlmCallLogEntity] = []

    def insert(self, log: LlmCallLogEntity) -> None:
        self.inserted.append(log)


class _FlakyRepository:
    """Raises on the first `insert`, succeeds on every subsequent call."""

    def __init__(self) -> None:
        self.inserted: list[LlmCallLogEntity] = []
        self._raised_once = False

    def insert(self, log: LlmCallLogEntity) -> None:
        if not self._raised_once:
            self._raised_once = True
            raise RuntimeError("db unreachable")
        self.inserted.append(log)


class _BlockingRepository:
    """Blocks `insert` on an event, to prove `track()` does not wait for it."""

    def __init__(self, release: threading.Event, entered: threading.Event) -> None:
        self._release = release
        self._entered = entered

    def insert(self, log: LlmCallLogEntity) -> None:
        self._entered.set()
        self._release.wait(timeout=5)


def _make_log(cost_usd: Decimal | None = Decimal("0.001234")) -> LlmCallLogEntity:
    return LlmCallLogEntity(
        caller="test_agent",
        model="openrouter/anthropic/claude-3.5-sonnet",
        prompt="Domanda.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=cost_usd,
        latency_ms=42,
    )


def test_track_persists_cost_unchanged() -> None:
    repository = _FakeRepository()

    with QueuedLlmCallTracker(repository) as tracker:
        tracker.track(_make_log())

    assert len(repository.inserted) == 1
    assert repository.inserted[0].cost_usd == Decimal("0.001234")


def test_repository_failure_degrades(caplog: pytest.LogCaptureFixture) -> None:
    repository = _FlakyRepository()

    with (
        caplog.at_level(logging.WARNING),
        QueuedLlmCallTracker(repository) as tracker,
    ):
        tracker.track(_make_log())
        tracker.track(_make_log())

    assert len(repository.inserted) == 1, "the second log must still be persisted"
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_close_flushes_pending() -> None:
    repository = _FakeRepository()
    tracker = QueuedLlmCallTracker(repository)
    tracker.__enter__()

    for _ in range(20):
        tracker.track(_make_log())
    tracker.close()

    assert len(repository.inserted) == 20


def test_track_does_not_block() -> None:
    release = threading.Event()
    entered = threading.Event()
    tracker = QueuedLlmCallTracker(_BlockingRepository(release, entered))

    with tracker:
        start = time.perf_counter()
        tracker.track(_make_log())
        elapsed = time.perf_counter() - start

        assert entered.wait(timeout=5), "the worker thread never picked up the item"
        assert elapsed < 0.05, "track() must return immediately, not wait on the insert"
        release.set()
