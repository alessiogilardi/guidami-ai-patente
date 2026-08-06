"""`ingest evaluate retrieval` dispatch: measures retrieval quality (spec 0007)."""

import argparse
import logging
from pathlib import Path

from rich.console import Console

from guidami_ai_patente_ingestor.cli.models.evaluation import QuestionOutcome
from guidami_ai_patente_ingestor.cli.models.run_artifacts import EvaluateManifest
from guidami_ai_patente_ingestor.configs import EvaluationConfig, IngestorConfig

from .. import wiring
from ..rendering import render_dry_run, render_evaluation
from ..services.evaluation import EvaluationArtifactWriter, RetrievalEvaluator

logger = logging.getLogger(__name__)


def _effective_config(config: IngestorConfig, args: argparse.Namespace) -> EvaluationConfig:
    """Layers `--seed`/`--baseline-repetitions` (when given) over `config.evaluation`.

    FR-1: every run parameter is supplied from configuration, with CLI flags
    overriding where useful; `args.seed`/`args.baseline_repetitions` default to `None`,
    meaning "use config".
    """
    overrides = {
        name: value
        for name, value in (
            ("seed", args.seed),
            ("baseline_repetitions", args.baseline_repetitions),
        )
        if value is not None
    }
    return config.evaluation.model_copy(update=overrides)


def _judge_subset(
    outcomes: list[QuestionOutcome], config: EvaluationConfig
) -> list[QuestionOutcome]:
    """FR-9's undecidable subset: keyword "matches nothing" plus non-selective-only hits."""
    largest_cutoff = max(config.keyword_df_cutoffs)
    return [
        outcome
        for outcome in outcomes
        if outcome.keyword_measurable
        and (outcome.keyword_best_df is None or outcome.keyword_best_df > largest_cutoff)
    ]


def run_evaluate(
    config: IngestorConfig,
    args: argparse.Namespace,
    manifest: EvaluateManifest | None,
    run_dir: Path | None = None,
) -> None:
    """Dispatch `evaluate retrieval`: measure retrieval quality against the quiz bank.

    `--dry-run` prints the step chain (`RetrievalEvaluator.STEP_NAMES`, PD-5) and
    returns *before* `wiring.build_postgres_client` is ever called (FR-1): no DB
    connection is opened, and no filesystem write happens either. FR-8 holds trivially
    on this path since a dry run makes no call of any kind.
    """
    if args.dry_run:
        render_dry_run(Console(), "evaluate", list(RetrievalEvaluator.STEP_NAMES))
        return

    assert manifest is not None
    assert run_dir is not None
    effective_config = _effective_config(config, args)
    manifest.record_parameters(effective_config)

    with wiring.build_postgres_client(config) as postgres_client:
        repositories = wiring.build_evaluation_repositories(config, postgres_client)
        evaluator = RetrievalEvaluator(effective_config, repositories.quiz, repositories.corpus)
        logger.info("starting retrieval evaluation")
        summary, outcomes = evaluator.evaluate()
        logger.info("retrieval evaluation completed")

    writer = EvaluationArtifactWriter(effective_config.output_dir, run_dir)
    writer.write_summary(summary)
    writer.write_detail(outcomes)
    writer.write_judge_export(_judge_subset(outcomes, effective_config))
    render_evaluation(summary, Console(), plain=args.plain)
