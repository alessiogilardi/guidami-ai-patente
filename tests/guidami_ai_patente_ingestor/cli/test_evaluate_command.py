"""Tests for cli/commands/evaluate.py (T-11, extended by T-17)."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from guidami_ai_patente_ingestor.cli.services.evaluation.multi_arm_retrieval_evaluator import (
    MultiArmRetrievalEvaluator,
)


def test_dry_run_opens_no_connection(capsys: pytest.CaptureFixture[str]) -> None:
    """FR-1: `--dry-run` prints the step chain and returns before any DB connection opens.

    The printed chain derives from `MultiArmRetrievalEvaluator.STEP_NAMES` (T-17, PD-5),
    not from a hand-maintained parallel list.
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
    for step in MultiArmRetrievalEvaluator.STEP_NAMES:
        assert step in output


def test_run_evaluate_writes_multi_arm_summary(tmp_path) -> None:
    """T-17: `run_evaluate` uses `MultiArmRetrievalEvaluator`, not `RetrievalEvaluator`."""
    args = argparse.Namespace(
        entity="retrieval", dry_run=False, plain=True, seed=None, baseline_repetitions=None
    )
    manifest = MagicMock()
    fake_summary = MagicMock(name="MultiArmEvaluationSummary")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.evaluate.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.evaluate.wiring.build_evaluation_repositories"
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.evaluate.MultiArmRetrievalEvaluator"
        ) as evaluator_cls,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.evaluate.EvaluationArtifactWriter"
        ) as writer_cls,
        patch("guidami_ai_patente_ingestor.cli.commands.evaluate.render_evaluation"),
    ):
        evaluator_cls.return_value.evaluate.return_value = (fake_summary, [])

        from guidami_ai_patente_ingestor.cli.commands.evaluate import run_evaluate

        run_evaluate(MagicMock(), args, manifest, tmp_path)

    written_summary = writer_cls.return_value.write_summary.call_args[0][0]
    assert written_summary is fake_summary


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
