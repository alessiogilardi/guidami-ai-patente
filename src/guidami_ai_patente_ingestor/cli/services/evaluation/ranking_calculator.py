"""Ranking metrics and random baseline (FR-3, FR-4)."""

import statistics
from collections.abc import Mapping, Sequence

from domain.models.retrieval import RetrievedComma
from guidami_ai_patente_ingestor.cli.models.evaluation import (
    QuestionOutcome,
    RankingAtK,
    RankingReport,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig

from .keyword_matching import corpus_haystack, matches_any_keyword

__all__ = ["RankingCalculator", "RankingReport"]

_IDENTITY_NOTE = (
    "Coverage and ranking match identically (FR-2), so an uncovered question is a miss "
    "by construction: full ≈ covered × coverage_rate. The gap between the two "
    "denominators is an arithmetic identity, not a measured retrieval cost."
)
_IMAGE_COMPARABILITY_NOTE = (
    "Image and non-image questions are not comparable to each other on this metric: "
    "keyword selectivity differs between the two populations."
)


def _hit_rate(outcomes: Sequence[QuestionOutcome], k: int) -> float:
    """Share of `outcomes` that hit at `k`, `0.0` on an empty population."""
    if not outcomes:
        return 0.0
    return sum(1 for outcome in outcomes if outcome.hits.get(k, False)) / len(outcomes)


def _is_covered(outcome: QuestionOutcome) -> bool:
    """True when `outcome`'s question is in FR-4's keyword-derived covered subset."""
    return outcome.keyword_measurable and outcome.keyword_best_df is not None


class RankingCalculator:
    """Computes FR-4's hit@k (both denominators) and FR-3's random-baseline lift."""

    def __init__(self, config: EvaluationConfig) -> None:
        """Injects the run config (the `k` values to report at)."""
        self._config = config

    def is_hit(
        self, keywords: list[str] | None, retrieved: Sequence[RetrievedComma], k: int
    ) -> bool:
        """True when any of `keywords` matches within the first `k` retrieved commas.

        Builds its haystack via `corpus_haystack`, never by inlining the f-string, so
        this stays the exact mirror of `CorpusReadRepository.keyword_document_frequency`'s
        SQL haystack (FR-2's identical-fields criterion).
        """
        if not keywords:
            return False
        return any(
            matches_any_keyword(keywords, corpus_haystack(comma.article_title, comma.text))
            for comma in retrieved[:k]
        )

    def build_report(
        self,
        per_question: Sequence[QuestionOutcome],
        baselines: Sequence[Mapping[int, float]],
    ) -> RankingReport:
        """Aggregates hit@k (covered + full denominators) and the baseline lift, per `k`.

        `by_topic`/`by_image` repeat the same `at_k` computation over each subgroup, so
        FR-4's topic and image/non-image breakdowns share one definition with the
        overall figures.
        """
        at_k = {k: self._at_k(per_question, baselines, k) for k in self._config.k_values}
        by_topic = {
            topic: {
                k: self._at_k(
                    [outcome for outcome in per_question if outcome.row.topic == topic],
                    baselines,
                    k,
                )
                for k in self._config.k_values
            }
            for topic in dict.fromkeys(outcome.row.topic for outcome in per_question)
        }
        by_image = {
            has_image: {
                k: self._at_k(
                    [
                        outcome
                        for outcome in per_question
                        if bool(outcome.row.image_filename) == has_image
                    ],
                    baselines,
                    k,
                )
                for k in self._config.k_values
            }
            for has_image in (True, False)
        }
        return RankingReport(
            at_k=at_k,
            by_topic=by_topic,
            by_image=by_image,
            identity_note=_IDENTITY_NOTE,
            image_comparability_note=_IMAGE_COMPARABILITY_NOTE,
        )

    def _at_k(
        self,
        per_question: Sequence[QuestionOutcome],
        baselines: Sequence[Mapping[int, float]],
        k: int,
    ) -> RankingAtK:
        covered = [outcome for outcome in per_question if _is_covered(outcome)]
        hit_covered = _hit_rate(covered, k)
        hit_full = _hit_rate(per_question, k)
        baseline_values = [baseline[k] for baseline in baselines]
        baseline_mean = statistics.mean(baseline_values) if baseline_values else 0.0
        baseline_spread_pp = (
            (max(baseline_values) - min(baseline_values)) * 100 if baseline_values else 0.0
        )
        lift_ratio = hit_full / baseline_mean if baseline_mean else float("nan")
        lift_points = (hit_full - baseline_mean) * 100
        return RankingAtK(
            hit_covered=hit_covered,
            hit_full=hit_full,
            baseline_mean=baseline_mean,
            baseline_spread_pp=baseline_spread_pp,
            lift_ratio=lift_ratio,
            lift_points=lift_points,
        )
