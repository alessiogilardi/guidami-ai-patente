"""Tests for LiveDashboard — one Live, three bars, one bordered log panel.

Per PD-8 / the spec's testing Constraint, assertions read `Progress.tasks` state,
never rendered output. The dashboard's `__enter__`/`__exit__` (which start/stop the
`Live` and attach/detach the log handler) are exercised separately from the pure
progress-state transitions, which are checked without entering the context manager.
"""

import logging
from io import StringIO

from rich.console import Console

from guidami_ai_patente_ingestor.cli.rendering.dashboard import LiveDashboard, LogPanelHandler


def _make_dashboard() -> LiveDashboard:
    console = Console(force_terminal=True, width=100, file=StringIO())
    return LiveDashboard(console, LogPanelHandler())


def _task_by_description_prefix(dashboard: LiveDashboard, prefix: str):  # noqa: ANN202
    matches = [t for t in dashboard._progress.tasks if t.description.startswith(prefix)]  # noqa: SLF001
    assert len(matches) == 1, f"expected exactly one task starting with {prefix!r}"
    return matches[0]


def test_step_bar_shows_position_at_start_and_advances_at_end() -> None:
    dashboard = _make_dashboard()

    dashboard.begin_run(2)
    dashboard.begin_flow("knowledge_cleaning")
    dashboard.begin_step("clean_articles", 2, 4)

    task = _task_by_description_prefix(dashboard, "2/4")
    assert task.description == "2/4 clean_articles"
    assert task.completed == 1.0

    dashboard.end_step()

    task = _task_by_description_prefix(dashboard, "2/4")
    assert task.completed == 2.0


def test_begin_items_twice_in_a_row_leaves_exactly_one_item_task() -> None:
    dashboard = _make_dashboard()
    dashboard.begin_run(1)
    dashboard.begin_flow("quiz_enrichment")
    dashboard.begin_step("enrich_quiz", 1, 1)

    dashboard.begin_items("images", 3)
    dashboard.begin_items("questions", 2)

    matches = [t for t in dashboard._progress.tasks if t.description in ("images", "questions")]  # noqa: SLF001
    assert len(matches) == 1
    assert matches[0].description == "questions"
    assert matches[0].total == 2


def test_end_step_removes_an_open_item_task() -> None:
    dashboard = _make_dashboard()
    dashboard.begin_run(1)
    dashboard.begin_flow("knowledge_enrichment")
    dashboard.begin_step("enrich_articles", 1, 1)
    dashboard.begin_items("articles", 3)

    dashboard.end_step()

    assert dashboard._items_task is None  # noqa: SLF001
    assert not any(t.description == "articles" for t in dashboard._progress.tasks)  # noqa: SLF001


def test_advance_item_never_pushes_completed_above_total() -> None:
    dashboard = _make_dashboard()
    dashboard.begin_run(1)
    dashboard.begin_flow("knowledge_indexing")
    dashboard.begin_step("embed_chunks", 1, 1)
    dashboard.begin_items("batches", 2)

    dashboard.advance_item()
    dashboard.advance_item()

    task = _task_by_description_prefix(dashboard, "batches")
    assert task.completed == 2.0
    assert task.total == 2


def test_end_flow_sets_flow_task_completed_to_flow_index() -> None:
    dashboard = _make_dashboard()
    dashboard.begin_run(2)
    dashboard.begin_flow("knowledge_cleaning")

    dashboard.end_flow()

    flow_task = next(
        t
        for t in dashboard._progress.tasks
        if t.description.startswith("1/2")  # noqa: SLF001
    )
    assert flow_task.completed == 1.0


def test_exit_detaches_handler_from_root_logger() -> None:
    dashboard = _make_dashboard()

    with dashboard:
        assert dashboard.log_handler in logging.getLogger().handlers

    assert dashboard.log_handler not in logging.getLogger().handlers
