"""Tests for LogPanelHandler — bounded, filtered log sink feeding the live dashboard."""

import logging

from guidami_ai_patente_ingestor.cli.rendering.dashboard import LogPanelHandler


def _make_handler() -> LogPanelHandler:
    handler = LogPanelHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _emit(handler: LogPanelHandler, logger_name: str, message: str) -> None:
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )
    handler.emit(record)


def test_retains_only_the_last_fifteen_records() -> None:
    handler = _make_handler()

    for i in range(20):
        _emit(handler, "guidami_ai_patente_ingestor.test", f"m{i}")

    snapshot = handler.snapshot()
    assert len(snapshot) == 15
    assert snapshot == [f"m{i}" for i in range(5, 20)]


def test_muted_third_party_loggers_are_excluded() -> None:
    handler = _make_handler()

    _emit(handler, "httpx", "httpx record")
    _emit(handler, "httpcore", "httpcore record")
    _emit(handler, "LiteLLM", "LiteLLM record")
    _emit(handler, "litellm.utils", "litellm.utils record")
    _emit(handler, "guidami_ai_patente_ingestor.orchestrators", "orchestrators record")
    _emit(handler, "flowstep.core.observability", "flowstep record")

    snapshot = handler.snapshot()
    assert "httpx record" not in snapshot
    assert "httpcore record" not in snapshot
    assert "LiteLLM record" not in snapshot
    assert "litellm.utils record" not in snapshot
    assert "orchestrators record" in snapshot
    assert "flowstep record" in snapshot
