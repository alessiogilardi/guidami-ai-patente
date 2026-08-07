"""Enumerates every stored (variant, model) arm and the fusion arm.

Evaluates each, and assembles FR-3's MultiArmEvaluationSummary.
"""

import logging
import statistics
from collections.abc import Sequence
from typing import Final, NamedTuple

from commons.ai.utils import reciprocal_rank_fusion
from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from domain.models.retrieval import QuizEvaluationRow, RetrievedComma
from guidami_ai_patente_ingestor.cli.models.evaluation import (
    ArmResult,
    EvaluationSummary,
    KeywordQualityReport,
    MultiArmEvaluationSummary,
    QuestionOutcome,
    RankingDelta,
    SignalReport,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig

from .adherence_calculator import AdherenceCalculator
from .coverage_calculator import CoverageCalculator
from .keyword_quality_calculator import KeywordQualityCalculator
from .ranking_calculator import RankingCalculator
from .retrieval_evaluator import RetrievalEvaluator

logger = logging.getLogger(__name__)

STEP_NAMES: Final[tuple[str, ...]] = (
    "enumerate arms",
    "load rows per arm",
    "evaluate each stored arm",
    "fusion arm",
    "compute deltas",
    "aggregate",
)

_FUSION_LABEL = "fusion"
# The fusion arm always fuses topic_text + text, plus image_description when the same
# question also has a row for it (PD-1).
_FUSION_REQUIRED_VARIANTS: Final[tuple[str, str]] = ("topic_text", "text")
_FUSION_OPTIONAL_VARIANT = "image_description"


def _median_and_quartiles(values: Sequence[float]) -> tuple[float, tuple[float, float]]:
    """Returns `(median, (q1, q3))`, `0.0` on an empty series.

    Duplicated from `retrieval_evaluator.py` (T-16's own judgment call, see Risks):
    `RetrievalEvaluator` exposes no public seam for the fusion arm's aggregation, which
    needs this exact helper, so it is kept as a tiny, private, module-level function here
    rather than reaching into `RetrievalEvaluator`'s private methods.
    """
    if not values:
        return 0.0, (0.0, 0.0)
    sorted_values = sorted(values)
    median = statistics.median(sorted_values)
    if len(sorted_values) < 2:
        return median, (median, median)
    quartiles = statistics.quantiles(sorted_values, n=4, method="inclusive")
    return median, (quartiles[0], quartiles[2])


class _FusionRow(NamedTuple):
    """One question's constituent vectors for the fusion arm (PD-1)."""

    row: QuizEvaluationRow
    topic_text_embedding: list[float]
    text_embedding: list[float]
    image_description_embedding: list[float] | None


class MultiArmRetrievalEvaluator:
    """Owns arm enumeration, per-arm evaluation, the fusion arm, and delta assembly."""

    STEP_NAMES: Final[tuple[str, ...]] = STEP_NAMES

    def __init__(
        self,
        config: EvaluationConfig,
        quiz_repository: QuizReadRepository,
        corpus_repository: CorpusReadRepository,
    ) -> None:
        """Injects the run config and the two read repositories."""
        self._config = config
        self._quiz_repository = quiz_repository
        self._corpus_repository = corpus_repository
        self._evaluator = RetrievalEvaluator(config, corpus_repository)
        self._coverage_calculator = CoverageCalculator(config, corpus_repository)
        self._ranking_calculator = RankingCalculator(config)
        self._adherence_calculator = AdherenceCalculator(config, corpus_repository)
        self._keyword_quality_calculator = KeywordQualityCalculator(corpus_repository)

    def evaluate(self) -> tuple[MultiArmEvaluationSummary, list[QuestionOutcome]]:
        """Runs every arm; returns the multi-arm summary and the baseline arm's outcomes.

        Raises `ValueError` if the configured baseline variant has no populated arm at
        all — naming the configured variant and the variants actually available, mirroring
        the single-arm harness's prior fail-loud behavior for a fully missing baseline.
        """
        rows_by_variant_and_model = self._load_all_stored_arms()
        arms: dict[str, ArmResult] = {}
        baseline_outcomes: list[QuestionOutcome] = []
        total_questions = len(
            {row.number for rows in rows_by_variant_and_model.values() for row in rows}
        )
        model_columns = self._quiz_repository.populated_model_columns()

        baseline_result: ArmResult | None = None
        for (variant, model_column), rows in rows_by_variant_and_model.items():
            label = variant if len(model_columns) <= 1 else f"{variant}::{model_column}"
            summary, outcomes = self._evaluator.evaluate(rows)
            result = ArmResult(
                label=label,
                variant=variant,
                model_column=model_column,
                question_count=len(rows),
                excluded_count=total_questions - len(rows),
                summary=summary,
                delta_vs_baseline=None,
            )
            arms[label] = result
            if variant == self._config.quiz_embedding_variant:
                baseline_result = result
                baseline_outcomes = outcomes

        if baseline_result is None:
            raise ValueError(
                f"no populated arm for configured baseline variant "
                f"{self._config.quiz_embedding_variant!r}; variants actually present: "
                f"{sorted({variant for variant, _ in rows_by_variant_and_model})!r}"
            )

        fusion_rows = self._load_fusion_rows(rows_by_variant_and_model)
        if fusion_rows:
            fusion_summary, _fusion_outcomes = self._evaluate_fusion_arm(fusion_rows)
            arms[_FUSION_LABEL] = ArmResult(
                label=_FUSION_LABEL,
                variant=None,
                model_column=None,
                question_count=len(fusion_rows),
                excluded_count=total_questions - len(fusion_rows),
                summary=fusion_summary,
                delta_vs_baseline=None,
            )

        for label, result in arms.items():
            if label != baseline_result.label:
                arms[label] = result.model_copy(
                    update={"delta_vs_baseline": self._delta(result, baseline_result)}
                )

        return (
            MultiArmEvaluationSummary(baseline_label=baseline_result.label, arms=arms),
            baseline_outcomes,
        )

    def _load_all_stored_arms(self) -> dict[tuple[str, str], list[QuizEvaluationRow]]:
        variants = self._quiz_repository.available_variants()
        model_columns = self._quiz_repository.populated_model_columns()
        result: dict[tuple[str, str], list[QuizEvaluationRow]] = {}
        for variant in variants:
            for model_column in model_columns:
                rows = self._quiz_repository.fetch_with_vectors(variant, model_column)
                if rows:
                    result[(variant, model_column)] = rows
        return result

    def _delta(self, arm: ArmResult, baseline: ArmResult) -> RankingDelta:
        return RankingDelta(
            hit_full_delta_points={
                k: (at_k.hit_full - baseline.summary.ranking.at_k[k].hit_full) * 100
                for k, at_k in arm.summary.ranking.at_k.items()
                if k in baseline.summary.ranking.at_k
            }
        )

    def _first_populated_rows(
        self,
        rows_by_variant_and_model: dict[tuple[str, str], list[QuizEvaluationRow]],
        variant: str,
    ) -> list[QuizEvaluationRow] | None:
        """Returns `variant`'s rows under the first (alphabetical) populated model column.

        `None` when `variant` has no populated arm at all. PD-1 does not vary the fusion
        arm by model, so any one populated model column is as good as another.
        """
        matching_model_columns = sorted(
            model_column
            for (arm_variant, model_column) in rows_by_variant_and_model
            if arm_variant == variant
        )
        if not matching_model_columns:
            return None
        return rows_by_variant_and_model[(variant, matching_model_columns[0])]

    def _load_fusion_rows(
        self, rows_by_variant_and_model: dict[tuple[str, str], list[QuizEvaluationRow]]
    ) -> list[_FusionRow]:
        """Builds the fusion arm's question population (PD-1).

        The intersection (by `.number`) of the `topic_text` and `text` arms, both
        required; `image_description` joins in only for the questions that also have a
        row there.
        """
        topic_text_rows = self._first_populated_rows(rows_by_variant_and_model, "topic_text")
        text_rows = self._first_populated_rows(rows_by_variant_and_model, "text")
        if not topic_text_rows or not text_rows:
            return []

        text_by_number = {row.number: row for row in text_rows}
        image_rows = (
            self._first_populated_rows(rows_by_variant_and_model, _FUSION_OPTIONAL_VARIANT) or []
        )
        image_by_number = {row.number: row for row in image_rows}

        fusion_rows: list[_FusionRow] = []
        for topic_row in topic_text_rows:
            text_row = text_by_number.get(topic_row.number)
            if text_row is not None:
                image_row = image_by_number.get(topic_row.number)
                fusion_rows.append(
                    _FusionRow(
                        row=text_row,
                        topic_text_embedding=topic_row.embedding,
                        text_embedding=text_row.embedding,
                        image_description_embedding=(
                            image_row.embedding if image_row is not None else None
                        ),
                    )
                )
        return fusion_rows

    def _field_adherences(
        self, lexemes: list[str], dense: list[RetrievedComma]
    ) -> tuple[float, float]:
        """Title-only/text-only `ts_rank` of the top-1 fused comma.

        Mirrors `RetrievalEvaluator._field_adherences`, FR-5 per-field report.
        """
        if not dense:
            return 0.0, 0.0
        top = dense[0]
        _weighted, title_only, text_only = self._corpus_repository.rank_text(
            lexemes, top.article_title, top.text
        )
        return title_only, text_only

    def _fuse_dense(self, fusion_row: _FusionRow, depth: int) -> list[RetrievedComma]:
        """Fuses each constituent vector's own `dense_top_k` ranking via RRF (AD-3).

        No fused vector is ever queried or stored: each constituent vector is retrieved
        independently, and only the resulting rankings are fused, by citation identity.
        """
        vectors = [fusion_row.topic_text_embedding, fusion_row.text_embedding]
        if fusion_row.image_description_embedding is not None:
            vectors.append(fusion_row.image_description_embedding)
        rankings = [self._corpus_repository.dense_top_k(vector, depth) for vector in vectors]
        citation_rankings = [[comma.citation for comma in ranking] for ranking in rankings]
        fused_citations = reciprocal_rank_fusion(citation_rankings, self._config.rrf_k)
        comma_by_citation = {comma.citation: comma for ranking in rankings for comma in ranking}
        return [comma_by_citation[citation] for citation in fused_citations][:depth]

    def _baseline_repetition(
        self, rows: list[QuizEvaluationRow], repetition: int, depth: int
    ) -> dict[int, float]:
        """Mirrors `RetrievalEvaluator._baseline_repetition`.

        See the module docstring on `_median_and_quartiles` for why this is duplicated
        rather than reused.
        """
        if not rows:
            return dict.fromkeys(self._config.k_values, 0.0)
        random_draws = [
            self._corpus_repository.random_top_k(
                depth, seed_key=f"{self._config.seed}:{repetition}:{row.number}"
            )
            for row in rows
        ]
        return {
            k: sum(
                1
                for row, draw in zip(rows, random_draws, strict=True)
                if self._ranking_calculator.is_hit(row.exact_keywords, draw, k)
            )
            / len(rows)
            for k in self._config.k_values
        }

    def _evaluate_fusion_arm(
        self, fusion_rows: list[_FusionRow]
    ) -> tuple[EvaluationSummary, list[QuestionOutcome]]:
        """Computes the fusion arm's full `EvaluationSummary`.

        Reuses the same four calculators `RetrievalEvaluator` uses, but with a fused (not
        stored) dense ranking per question.
        """
        depth = max(self._config.k_values)
        rows = [fusion_row.row for fusion_row in fusion_rows]
        dense_top_k = [self._fuse_dense(fusion_row, depth) for fusion_row in fusion_rows]
        fts_top_k = [
            self._corpus_repository.text_top_k(
                self._adherence_calculator.build_tsquery(row.text), depth
            )
            for row in rows
        ]
        text_scores = [self._coverage_calculator.text_score(row.text) for row in rows]
        keyword_best_dfs = [
            self._coverage_calculator.keyword_best_document_frequency(row.exact_keywords)
            if row.exact_keywords
            else None
            for row in rows
        ]
        hits = [
            {
                k: self._ranking_calculator.is_hit(row.exact_keywords, dense, k)
                for k in self._config.k_values
            }
            for row, dense in zip(rows, dense_top_k, strict=True)
        ]
        baselines = [
            self._baseline_repetition(rows, repetition, depth)
            for repetition in range(self._config.baseline_repetitions)
        ]

        top1_adherences: list[float] = []
        title_adherences: list[float] = []
        text_adherences: list[float] = []
        dense_fts_overlaps: list[float] = []
        distance_margins: list[float] = []
        for row, dense, fts in zip(rows, dense_top_k, fts_top_k, strict=True):
            lexemes = self._adherence_calculator.build_tsquery(row.text)
            top1_adherences.append(self._adherence_calculator.top1_adherence(lexemes, dense))
            title_only, text_only = self._field_adherences(lexemes, dense)
            title_adherences.append(title_only)
            text_adherences.append(text_only)
            dense_fts_overlaps.append(self._adherence_calculator.dense_fts_overlap(dense, fts))
            distance_margins.append(self._adherence_calculator.distance_margin(dense))

        outcomes = [
            QuestionOutcome(
                row=row,
                dense_top_k=dense,
                fts_top_k=fts,
                text_coverage=text_score,
                keyword_best_df=keyword_best_df,
                keyword_measurable=bool(row.exact_keywords),
                hits=hit,
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
                hit,
                top1_adherence,
                overlap,
                margin,
            ) in zip(
                rows,
                dense_top_k,
                fts_top_k,
                text_scores,
                keyword_best_dfs,
                hits,
                top1_adherences,
                dense_fts_overlaps,
                distance_margins,
                strict=True,
            )
        ]

        distinct_keywords = sorted(
            {keyword for row in rows if row.exact_keywords for keyword in row.exact_keywords}
        )
        representative_k = min(self._config.k_values)
        hits_at_representative_k = [hit.get(representative_k, False) for hit in hits]
        association = self._keyword_quality_calculator.hit_adherence_association(
            hits_at_representative_k, top1_adherences
        )
        keyword_quality_report = KeywordQualityReport(
            zero_match_share=self._keyword_quality_calculator.zero_match_share(distinct_keywords),
            document_frequency_distribution=(
                self._keyword_quality_calculator.document_frequency_distribution(distinct_keywords)
            ),
            hit_adherence_association=association,
        )

        summary = EvaluationSummary(
            schema_version=1,
            parameters=self._config,
            coverage=self._coverage_calculator.build_report(rows, text_scores, keyword_best_dfs),
            ranking=self._ranking_calculator.build_report(outcomes, baselines),
            signals=self._build_signal_report(
                top1_adherences,
                title_adherences,
                text_adherences,
                dense_fts_overlaps,
                distance_margins,
            ),
            keyword_quality=keyword_quality_report,
        )
        return summary, outcomes

    @staticmethod
    def _build_signal_report(
        top1_adherences: list[float],
        title_adherences: list[float],
        text_adherences: list[float],
        dense_fts_overlaps: list[float],
        distance_margins: list[float],
    ) -> SignalReport:
        adherence_median, adherence_quartiles = _median_and_quartiles(top1_adherences)
        title_median, _title_quartiles = _median_and_quartiles(title_adherences)
        text_median, _text_quartiles = _median_and_quartiles(text_adherences)
        overlap_median, overlap_quartiles = _median_and_quartiles(dense_fts_overlaps)
        margin_median, margin_quartiles = _median_and_quartiles(distance_margins)
        zero_overlap_share = (
            sum(1 for overlap in dense_fts_overlaps if overlap == 0.0) / len(dense_fts_overlaps)
            if dense_fts_overlaps
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
