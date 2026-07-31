"""Shared root fixtures for the test suite."""

from dataclasses import dataclass, field

import pytest


@dataclass
class RecordingProgressReporter:
    """Test double for `ProgressReporter` recording every call in order.

    Each method appends `(method_name, args)` to `calls`, in the exact order and
    arity the corresponding protocol method receives them. `count` is a convenience
    for asserting how many times a given method fired, without slicing `calls`
    by hand in every test.
    """

    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def begin_run(self, total_flows: int) -> None:
        self.calls.append(("begin_run", (total_flows,)))

    def begin_flow(self, name: str) -> None:
        self.calls.append(("begin_flow", (name,)))

    def end_flow(self) -> None:
        self.calls.append(("end_flow", ()))

    def begin_step(self, name: str, index: int, total: int) -> None:
        self.calls.append(("begin_step", (name, index, total)))

    def end_step(self) -> None:
        self.calls.append(("end_step", ()))

    def begin_items(self, label: str, total: int) -> None:
        self.calls.append(("begin_items", (label, total)))

    def advance_item(self) -> None:
        self.calls.append(("advance_item", ()))

    def end_items(self) -> None:
        self.calls.append(("end_items", ()))

    def count(self, method: str) -> int:
        """Returns how many times `method` was called."""
        return sum(1 for name, _ in self.calls if name == method)


@pytest.fixture
def progress_recorder() -> RecordingProgressReporter:
    """A fresh `RecordingProgressReporter`, one per test."""
    return RecordingProgressReporter()
