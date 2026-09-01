import logging
import threading
import time

import pytest

from commons.ai.observability import LlmCallLogEntity, QueuedLlmCallTracker, TrackedCaller

_CALLER = TrackedCaller(caller="agent", model="m", system_prompt=None, expects_cost=False)


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


class _RecordingRepository:
    """Collects inserted logs in memory, in insertion order."""

    def __init__(self) -> None:
        self.logs: list[LlmCallLogEntity] = []

    def insert(self, log: LlmCallLogEntity) -> None:
        self.logs.append(log)


def test_track_persists_cost_unchanged() -> None:
    repository = _FakeRepository()

    with QueuedLlmCallTracker(5.0, repository) as tracker, tracker.track(_CALLER, "prompt"):
        pass

    assert len(repository.inserted) == 1
    assert repository.inserted[0].prompt == "prompt"


def test_repository_failure_degrades(caplog: pytest.LogCaptureFixture) -> None:
    repository = _FlakyRepository()

    with (
        caplog.at_level(logging.WARNING),
        QueuedLlmCallTracker(5.0, repository) as tracker,
    ):
        with tracker.track(_CALLER, "prompt"):
            pass
        with tracker.track(_CALLER, "prompt"):
            pass

    assert len(repository.inserted) == 1, "the second log must still be persisted"
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_close_flushes_pending() -> None:
    repository = _FakeRepository()
    tracker = QueuedLlmCallTracker(5.0, repository)
    tracker.__enter__()

    for _ in range(20):
        with tracker.track(_CALLER, "prompt"):
            pass
    tracker.close()

    assert len(repository.inserted) == 20


def test_track_does_not_block() -> None:
    release = threading.Event()
    entered = threading.Event()
    tracker = QueuedLlmCallTracker(5.0, _BlockingRepository(release, entered))

    with tracker:
        start = time.perf_counter()
        with tracker.track(_CALLER, "prompt"):
            pass
        elapsed = time.perf_counter() - start

        assert entered.wait(timeout=5), "the worker thread never picked up the item"
        assert elapsed < 0.05, "track() must return immediately, not wait on the insert"
        release.set()


def test_persists_one_row_per_tracked_call() -> None:
    repository = _RecordingRepository()

    with QueuedLlmCallTracker(1.0, repository) as tracker, tracker.track(_CALLER, "prompt"):
        pass

    assert len(repository.logs) == 1
    assert repository.logs[0].prompt == "prompt"


def test_persists_the_call_even_when_it_raises() -> None:
    repository = _RecordingRepository()

    with (
        QueuedLlmCallTracker(1.0, repository) as tracker,
        pytest.raises(ValueError),
        tracker.track(_CALLER, "prompt"),
    ):
        raise ValueError("boom")

    assert len(repository.logs) == 1
    assert repository.logs[0].status == "error"
