"""Evaluation orchestration: one pass building per-question outcomes, then aggregation."""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from guidami_ai_patente_ingestor.cli.models.evaluation import (
    EvaluationSummary,
    KeywordQualityReport,
    QuestionOutcome,
    SignalReport,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig

from .adherence_calculator import AdherenceCalculator
from .coverage_calculator import CoverageCalculator
from .keyword_quality_calculator import KeywordQualityCalculator
from .ranking_calculator import RankingCalculator

STEP_NAMES: Final[tuple[str, ...]] = (
    "dense retrieval",
    "text retrieval",
    "coverage",
    "ranking + baseline",
    "adherence + signals",
    "keyword quality",
    "aggregate",
)


def _median_and_quartiles(values: Sequence[float]) -> tuple[float, tuple[float, float]]:
    """Returns `(median, (q1, q3))`, `0.0` on an empty series."""
    if not values:
        return 0.0, (0.0, 0.0)
    sorted_values = sorted(values)
    median = statistics.median(sorted_values)
    if len(sorted_values) < 2:
        return median, (median, median)
    quartiles = statistics.quantiles(sorted_values, n=4, method="inclusive")
    return median, (quartiles[0], quartiles[2])


@dataclass
class _RunState:
    """Mutable accumulator for the single pass (PD-8): one entry per question, in order."""

    rows: list[QuizEvaluationRow] = field(default_factory=list)
    dense_top_k: list[list[RetrievedComma]] = field(default_factory=list)
    fts_top_k: list[list[RetrievedComma]] = field(default_factory=list)
    text_scores: list[float] = field(default_factory=list)
    keyword_best_dfs: list[int | None] = field(default_factory=list)
    hits: list[dict[int, bool]] = field(default_factory=list)
    baselines: list[dict[int, float]] = field(default_factory=list)
    top1_adherences: list[float] = field(default_factory=list)
    title_adherences: list[float] = field(default_factory=list)
    text_adherences: list[float] = field(default_factory=list)
    dense_fts_overlaps: list[float] = field(default_factory=list)
    distance_margins: list[float] = field(default_factory=list)
    keyword_quality_report: KeywordQualityReport | None = None
    outcomes: list[QuestionOutcome] = field(default_factory=list)
    summary: EvaluationSummary | None = None


class RetrievalEvaluator:
    """Sequences the full evaluation run (PD-8) and exposes its step declaration (PD-5).

    `STEP_NAMES` and the executed steps cannot drift: both the real run
    (`_steps`/`evaluate`) and the dry-run renderer (`commands/evaluate.py`) consume this
    same tuple.
    """

    STEP_NAMES: Final[tuple[str, ...]] = STEP_NAMES

    def __init__(
        self,
        config: EvaluationConfig,
        corpus_repository: CorpusReadRepository,
    ) -> None:
        """Injects the run config and the corpus read repository."""
        self._config = config
        self._corpus_repository = corpus_repository
        self._coverage_calculator = CoverageCalculator(config, corpus_repository)
        self._ranking_calculator = RankingCalculator(config)
        self._adherence_calculator = AdherenceCalculator(config, corpus_repository)
        self._keyword_quality_calculator = KeywordQualityCalculator(corpus_repository)

    def evaluate(
        self, rows: list[QuizEvaluationRow]
    ) -> tuple[EvaluationSummary, list[QuestionOutcome]]:
        """Runs every step in `STEP_NAMES` order over `rows`.

        Returns the summary and per-question detail. `rows` is caller-supplied (T-14):
        this class no longer loads rows itself, so it no longer decides what an
        empty/missing arm means — that decision now belongs to the caller
        (`MultiArmRetrievalEvaluator`).
        """
        state = _RunState(rows=rows)
        for _name, step in self._steps():
            step(state)
        assert state.summary is not None
        return state.summary, state.outcomes

    def _steps(self) -> tuple[tuple[str, Callable[[_RunState], None]], ...]:
        return (
            ("dense retrieval", self._dense_retrieval),
            ("text retrieval", self._text_retrieval),
            ("coverage", self._coverage),
            ("ranking + baseline", self._ranking_and_baseline),
            ("adherence + signals", self._adherence_and_signals),
            ("keyword quality", self._keyword_quality),
            ("aggregate", self._aggregate),
        )

    def _dense_retrieval(self, state: _RunState) -> None:
        depth = max(self._config.k_values)
        state.dense_top_k = [
            self._corpus_repository.dense_top_k(row.embedding, depth) for row in state.rows
        ]

    def _text_retrieval(self, state: _RunState) -> None:
        depth = max(self._config.k_values)
        state.fts_top_k = [
            self._corpus_repository.text_top_k(
                self._adherence_calculator.build_tsquery(row.text), depth
            )
            for row in state.rows
        ]

    def _coverage(self, state: _RunState) -> None:
        state.text_scores = [self._coverage_calculator.text_score(row.text) for row in state.rows]
        state.keyword_best_dfs = [
            self._coverage_calculator.keyword_best_document_frequency(row.exact_keywords)
            if row.exact_keywords
            else None
            for row in state.rows
        ]

    def _ranking_and_baseline(self, state: _RunState) -> None:
        state.hits = [
            {
                k: self._ranking_calculator.is_hit(row.exact_keywords, dense, k)
                for k in self._config.k_values
            }
            for row, dense in zip(state.rows, state.dense_top_k, strict=True)
        ]
        depth = max(self._config.k_values)
        state.baselines = [
            self._baseline_repetition(state, repetition, depth)
            for repetition in range(self._config.baseline_repetitions)
        ]

    def _baseline_repetition(
        self, state: _RunState, repetition: int, depth: int
    ) -> dict[int, float]:
        """One reproducible baseline pass: a fresh random draw per question, hit rate per k.

        `0.0` on an empty `state.rows` (T-14: empty input is no longer fatal), matching
        `_hit_rate`'s identical "0.0 on empty population" convention.
        """
        if not state.rows:
            return dict.fromkeys(self._config.k_values, 0.0)
        random_draws = [
            self._corpus_repository.random_top_k(
                depth, seed_key=f"{self._config.seed}:{repetition}:{row.number}"
            )
            for row in state.rows
        ]
        return {
            k: sum(
                1
                for row, draw in zip(state.rows, random_draws, strict=True)
                if self._ranking_calculator.is_hit(row.exact_keywords, draw, k)
            )
            / len(state.rows)
            for k in self._config.k_values
        }

    def _adherence_and_signals(self, state: _RunState) -> None:
        for row, dense, fts in zip(state.rows, state.dense_top_k, state.fts_top_k, strict=True):
            lexemes = self._adherence_calculator.build_tsquery(row.text)
            state.top1_adherences.append(self._adherence_calculator.top1_adherence(lexemes, dense))
            title_only, text_only = self._field_adherences(lexemes, dense)
            state.title_adherences.append(title_only)
            state.text_adherences.append(text_only)
            state.dense_fts_overlaps.append(
                self._adherence_calculator.dense_fts_overlap(dense, fts)
            )
            state.distance_margins.append(self._adherence_calculator.distance_margin(dense))

    def _field_adherences(
        self, lexemes: list[str], dense: list[RetrievedComma]
    ) -> tuple[float, float]:
        """Title-only/text-only `ts_rank` of the top-1 dense comma (FR-5 per-field report)."""
        if not dense:
            return 0.0, 0.0
        top = dense[0]
        _weighted, title_only, text_only = self._corpus_repository.rank_text(
            lexemes, top.article_title, top.text
        )
        return title_only, text_only

    def _keyword_quality(self, state: _RunState) -> None:
        distinct_keywords = sorted(
            {keyword for row in state.rows if row.exact_keywords for keyword in row.exact_keywords}
        )
        representative_k = min(self._config.k_values)
        hits_at_representative_k = [hit.get(representative_k, False) for hit in state.hits]
        association = self._keyword_quality_calculator.hit_adherence_association(
            hits_at_representative_k, state.top1_adherences
        )
        state.keyword_quality_report = KeywordQualityReport(
            zero_match_share=self._keyword_quality_calculator.zero_match_share(distinct_keywords),
            document_frequency_distribution=(
                self._keyword_quality_calculator.document_frequency_distribution(distinct_keywords)
            ),
            hit_adherence_association=association,
        )

    def _aggregate(self, state: _RunState) -> None:
        state.outcomes = self._build_outcomes(state)
        assert state.keyword_quality_report is not None
        state.summary = EvaluationSummary(
            schema_version=1,
            parameters=self._config,
            coverage=self._coverage_calculator.build_report(
                state.rows, state.text_scores, state.keyword_best_dfs
            ),
            ranking=self._ranking_calculator.build_report(state.outcomes, state.baselines),
            signals=self._build_signal_report(state),
            keyword_quality=state.keyword_quality_report,
        )

    @staticmethod
    def _build_outcomes(state: _RunState) -> list[QuestionOutcome]:
        return [
            QuestionOutcome(
                row=row,
                dense_top_k=dense,
                fts_top_k=fts,
                text_coverage=text_score,
                keyword_best_df=keyword_best_df,
                keyword_measurable=bool(row.exact_keywords),
                hits=hits,
                top1_adherence=top1_adherence,
                dense_fts_overlap=overlap,
                distance_margin=margin,
            )
            for (
                row,
                dense,
                fts,
                text_score,
                keyword_best_df,
                hits,
                top1_adherence,
                overlap,
                margin,
            ) in zip(
                state.rows,
                state.dense_top_k,
                state.fts_top_k,
                state.text_scores,
                state.keyword_best_dfs,
                state.hits,
                state.top1_adherences,
                state.dense_fts_overlaps,
                state.distance_margins,
                strict=True,
            )
        ]

    @staticmethod
    def _build_signal_report(state: _RunState) -> SignalReport:
        adherence_median, adherence_quartiles = _median_and_quartiles(state.top1_adherences)
        title_median, _title_quartiles = _median_and_quartiles(state.title_adherences)
        text_median, _text_quartiles = _median_and_quartiles(state.text_adherences)
        overlap_median, overlap_quartiles = _median_and_quartiles(state.dense_fts_overlaps)
        margin_median, margin_quartiles = _median_and_quartiles(state.distance_margins)
        zero_overlap_share = (
            sum(1 for overlap in state.dense_fts_overlaps if overlap == 0.0)
            / len(state.dense_fts_overlaps)
            if state.dense_fts_overlaps
            else 0.0
        )
        return SignalReport(
            adherence_median=adherence_median,
            adherence_quartiles=adherence_quartiles,
            adherence_by_field={
                "weighted": adherence_median,
                "title": title_median,
                "text": text_median,
            },
            overlap_median=overlap_median,
            overlap_quartiles=overlap_quartiles,
            margin_median=margin_median,
            margin_quartiles=margin_quartiles,
            zero_overlap_share=zero_overlap_share,
        )
