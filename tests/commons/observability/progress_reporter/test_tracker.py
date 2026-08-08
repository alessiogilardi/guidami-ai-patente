from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from commons.observability import tracker

if TYPE_CHECKING:
    # `tests` has no `__init__.py` (project convention) and is not importable as a
    # dotted package at runtime under `uv run pytest <file>`. Type-only import,
    # resolved statically; pytest matches fixtures by parameter name, not annotation.
    from tests.conftest import RecordingProgressReporter


def test_begin_items_called_before_first_item_is_yielded(
    progress_recorder: RecordingProgressReporter,
) -> None:
    items = ["a", "b", "c"]
    iterator = tracker(progress_recorder, "batches", items)

    next(iterator)

    assert progress_recorder.calls[0] == ("begin_items", ("batches", 3))


def test_yields_items_in_original_order(progress_recorder: RecordingProgressReporter) -> None:
    items = ["a", "b", "c"]

    result = list(tracker(progress_recorder, "batches", items))

    assert result == items


def test_advance_item_fires_after_the_item_is_consumed_not_before(
    progress_recorder: RecordingProgressReporter,
) -> None:
    items = ["a", "b"]
    iterator = tracker(progress_recorder, "batches", items)

    first = next(iterator)
    assert first == "a"
    assert progress_recorder.count("advance_item") == 0

    second = next(iterator)
    assert second == "b"
    assert progress_recorder.count("advance_item") == 1


def test_end_items_called_once_iteration_is_exhausted(
    progress_recorder: RecordingProgressReporter,
) -> None:
    items = ["a", "b"]

    list(tracker(progress_recorder, "batches", items))

    assert progress_recorder.count("advance_item") == 2
    assert progress_recorder.calls[-1] == ("end_items", ())


def test_end_items_called_even_if_the_caller_raises_while_consuming_an_item(
    progress_recorder: RecordingProgressReporter,
) -> None:
    items = ["a", "b", "c"]

    with pytest.raises(RuntimeError):
        for item in tracker(progress_recorder, "batches", items):
            if item == "b":
                raise RuntimeError("boom")

    assert progress_recorder.calls[-1] == ("end_items", ())
