"""Tests for ProgressFlowObserver — adapts flowstep's FlowObserver onto a ProgressReporter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from flowstep import Step
from flowstep.core.observability.models import FlowProgress

from guidami_ai_patente_ingestor.orchestrators import ProgressFlowObserver

if TYPE_CHECKING:
    # `tests` has no `__init__.py` (project convention) and is not importable as a
    # dotted package at runtime under `uv run pytest <file>` (console-script entry
    # point does not add the project root to sys.path). Type-only import, resolved
    # statically; never evaluated at runtime thanks to `from __future__ import
    # annotations`. Pytest matches fixtures by parameter name, not by annotation.
    from tests.conftest import RecordingProgressReporter


def _make_step(name: str) -> Step:
    step = MagicMock(spec=Step)
    step.name = name
    return step


def test_on_start_reports_step_position(progress_recorder: RecordingProgressReporter) -> None:
    observer = ProgressFlowObserver(progress_recorder)
    step = _make_step("enrich_articles")

    observer.on_start(step, FlowProgress(index=4, total=5))
    observer.on_end(step, 12.5, FlowProgress(index=4, total=5))

    assert progress_recorder.calls == [
        ("begin_step", ("enrich_articles", 4, 5)),
        ("end_step", ()),
    ]


def test_on_error_also_emits_end_step(progress_recorder: RecordingProgressReporter) -> None:
    observer = ProgressFlowObserver(progress_recorder)
    step = _make_step("store_chunks")

    observer.on_start(step, FlowProgress(index=1, total=1))
    observer.on_error(step, ValueError("boom"), FlowProgress(index=1, total=1))

    assert progress_recorder.count("end_step") == 1
