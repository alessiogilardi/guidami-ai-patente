"""Tests for cli/commands/evaluate.py (T-11)."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from guidami_ai_patente_ingestor.cli.services.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
)


def test_dry_run_opens_no_connection(capsys: pytest.CaptureFixture[str]) -> None:
    """FR-1: `--dry-run` prints the step chain and returns before any DB connection opens.

    The printed chain derives from `RetrievalEvaluator.STEP_NAMES` (PD-5), not from a
    hand-maintained parallel list.
    """
    args = argparse.Namespace(
        entity="retrieval", dry_run=True, plain=False, seed=None, baseline_repetitions=None
    )

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.evaluate.wiring.build_postgres_client",
        side_effect=AssertionError("must not open a DB connection on --dry-run"),
    ) as pg:
        from guidami_ai_patente_ingestor.cli.commands.evaluate import run_evaluate

        run_evaluate(MagicMock(), args, None)

    pg.assert_not_called()
    output = capsys.readouterr().out
    for step in RetrievalEvaluator.STEP_NAMES:
        assert step in output


def test_runs_without_openrouter_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-8: a dry run completes without `OPENROUTER_API_KEY`.

    The evaluation harness makes no LLM calls at all.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    args = argparse.Namespace(
        entity="retrieval", dry_run=True, plain=False, seed=None, baseline_repetitions=None
    )

    with patch("guidami_ai_patente_ingestor.cli.commands.evaluate.wiring.build_postgres_client"):
        from guidami_ai_patente_ingestor.cli.commands.evaluate import run_evaluate

        run_evaluate(MagicMock(), args, None)
