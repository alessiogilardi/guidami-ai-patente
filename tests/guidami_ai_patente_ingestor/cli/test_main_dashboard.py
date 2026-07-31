"""Tests for `_build_dashboard` and the dashboard-aware dispatch in cli/main.py."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from rich.console import Console

if TYPE_CHECKING:
    pass  # placeholder retained for symmetry with sibling test files


@pytest.fixture(autouse=True)
def _reset_root_handlers() -> Iterator[None]:
    """Isolates each test from the root-logger state a dashboard's __enter__/__exit__ mutate.

    Mirrors the fixture in cli/test_logging_setup.py.
    """
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    for handler in root.handlers:
        if handler not in original_handlers:
            handler.close()
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def _prepare_args(*, dry_run: bool = False, plain: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        command="prepare", entity="knowledge", source="cds", dry_run=dry_run, plain=plain
    )


def test_no_dashboard_when_stdout_is_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from guidami_ai_patente_ingestor.cli.main import _build_dashboard

    monkeypatch.setattr(Console, "is_terminal", False)
    args = _prepare_args(dry_run=False, plain=False)

    assert _build_dashboard(args) is None


def test_plain_flag_on_tty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from guidami_ai_patente_ingestor.cli.main import _build_dashboard

    monkeypatch.setattr(Console, "is_terminal", True)
    args = _prepare_args(dry_run=False, plain=True)

    assert _build_dashboard(args) is None


def test_dry_run_on_tty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from guidami_ai_patente_ingestor.cli.main import _build_dashboard

    monkeypatch.setattr(Console, "is_terminal", True)
    args = _prepare_args(dry_run=True, plain=False)

    assert _build_dashboard(args) is None


def test_reset_command_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from guidami_ai_patente_ingestor.cli.main import _build_dashboard

    monkeypatch.setattr(Console, "is_terminal", True)
    args = argparse.Namespace(command="reset", entity="knowledge")

    assert _build_dashboard(args) is None


def test_tty_non_plain_non_dry_index_returns_a_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    from guidami_ai_patente_ingestor.cli.main import _build_dashboard
    from guidami_ai_patente_ingestor.cli.rendering.dashboard import LiveDashboard

    monkeypatch.setattr(Console, "is_terminal", True)
    args = argparse.Namespace(
        command="index", entity="knowledge", source="cds", dry_run=False, plain=False
    )

    dashboard = _build_dashboard(args)

    assert isinstance(dashboard, LiveDashboard)


def test_dashboard_torn_down_before_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-5: the dashboard's handler is detached from the root logger before propagation."""
    import importlib
    from io import StringIO

    from guidami_ai_patente_ingestor.cli.rendering.dashboard import LiveDashboard, LogPanelHandler

    # `import guidami_ai_patente_ingestor.cli.main as main_module` would bind to the
    # `main` *function* re-exported by `cli/__init__.py` (`from .main import main`),
    # not the submodule: `import a.b.c as x` resolves `x` through attribute access on
    # `a.b`, and that attribute is shadowed by the re-export. `importlib.import_module`
    # returns the actual cached submodule from `sys.modules`, sidestepping the shadow.
    main_module = importlib.import_module("guidami_ai_patente_ingestor.cli.main")

    dashboard = LiveDashboard(Console(force_terminal=True, file=StringIO()), LogPanelHandler())

    monkeypatch.setattr(main_module, "_build_dashboard", lambda args: dashboard)
    monkeypatch.setattr(main_module, "IngestorConfig", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(main_module.wiring, "build_layer_resolver", MagicMock())
    monkeypatch.setattr(main_module.wiring, "build_open_router_provider", MagicMock())
    fake_parser = MagicMock()
    fake_parser.parse_args.return_value = _prepare_args(dry_run=False, plain=False)
    monkeypatch.setattr(main_module, "build_parser", MagicMock(return_value=fake_parser))
    monkeypatch.setattr(main_module, "configure_logging", MagicMock(return_value=None))
    monkeypatch.setattr(
        main_module.prepare, "run_prepare", MagicMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        main_module.main()

    # The dashboard must actually have been entered (proving `main` engaged it, not
    # skipped it) and then torn down before the exception reached this test.
    assert dashboard.log_handler not in logging.getLogger().handlers
    assert not dashboard._live.is_started  # noqa: SLF001
