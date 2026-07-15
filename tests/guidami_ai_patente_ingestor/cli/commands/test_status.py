"""Tests for cli/commands/status.py."""

import argparse
from unittest.mock import MagicMock, patch

import psycopg


def test_online_db_unreachable_degrades() -> None:
    """--online with an unreachable Postgres renders db_reachable=False, no exception."""
    args = argparse.Namespace(online=True)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.status.StatusInspector",
        ) as inspector_class,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.status.wiring.build_postgres_client",
            side_effect=psycopg.OperationalError("connection refused"),
        ),
        patch("guidami_ai_patente_ingestor.cli.commands.status.render") as render_mock,
    ):
        inspector_class.return_value.evaluate_readiness.return_value = []
        from guidami_ai_patente_ingestor.cli.commands.status import run_status

        run_status(MagicMock(), MagicMock(), args)

    render_mock.assert_called_once()
    report = render_mock.call_args.args[1]
    assert report.db_reachable is False
    assert report.tables is None
