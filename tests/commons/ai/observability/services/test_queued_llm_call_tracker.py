import logging
import threading
import time
from decimal import Decimal

import pytest

from commons.ai.observability import QueuedLlmCallTracker
from domain.entities.observability import LlmCallLog


class _FakeRepository:
    """Collects inserted logs in memory, in insertion order."""

    def __init__(self) -> None:
        self.inserted: list[LlmCallLog] = []

    def insert(self, log: LlmCallLog) -> None:
        self.inserted.append(log)


class _FlakyRepository:
    """Raises on the first `insert`, succeeds on every subsequent call."""

    def __init__(self) -> None:
        self.inserted: list[LlmCallLog] = []
        self._raised_once = False

    def insert(self, log: LlmCallLog) -> None:
        if not self._raised_once:
            self._raised_once = True
            raise RuntimeError("db unreachable")
        self.inserted.append(log)


class _BlockingRepository:
    """Blocks `insert` on an event, to prove `track()` does not wait for it."""

    def __init__(self, release: threading.Event, entered: threading.Event) -> None:
        self._release = release
        self._entered = entered

    def insert(self, log: LlmCallLog) -> None:
        self._entered.set()
        self._release.wait(timeout=5)


class _StubCostCalculator:
    def cost_usd(self, model: str, input_tokens: int | None, output_tokens: int | None):
        return Decimal("0.001234")


def _make_log() -> LlmCallLog:
    return LlmCallLog(
        caller="test_agent",
        model="openrouter/anthropic/claude-3.5-sonnet",
        prompt="Domanda.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        latency_ms=42,
    )


def test_track_persists_with_cost() -> None:
    repository = _FakeRepository()

    with QueuedLlmCallTracker(repository, _StubCostCalculator()) as tracker:
        tracker.track(_make_log())

    assert len(repository.inserted) == 1
    assert repository.inserted[0].cost_usd == Decimal("0.001234")


def test_repository_failure_degrades(caplog: pytest.LogCaptureFixture) -> None:
    repository = _FlakyRepository()

    with (
        caplog.at_level(logging.WARNING),
        QueuedLlmCallTracker(repository, _StubCostCalculator()) as tracker,
    ):
        tracker.track(_make_log())
        tracker.track(_make_log())

    assert len(repository.inserted) == 1, "the second log must still be persisted"
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_close_flushes_pending() -> None:
    repository = _FakeRepository()
    tracker = QueuedLlmCallTracker(repository, _StubCostCalculator())
    tracker.__enter__()

    for _ in range(20):
        tracker.track(_make_log())
    tracker.close()

    assert len(repository.inserted) == 20


def test_track_does_not_block() -> None:
    release = threading.Event()
    entered = threading.Event()
    tracker = QueuedLlmCallTracker(_BlockingRepository(release, entered), _StubCostCalculator())

    with tracker:
        start = time.perf_counter()
        tracker.track(_make_log())
        elapsed = time.perf_counter() - start

        assert entered.wait(timeout=5), "the worker thread never picked up the item"
        assert elapsed < 0.05, "track() must return immediately, not wait on the insert"
        release.set()
