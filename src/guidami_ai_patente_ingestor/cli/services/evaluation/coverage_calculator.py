"""Corpus coverage metrics (FR-2): a continuous text score plus a keyword DF band."""

import re
import statistics
from collections.abc import Sequence

from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import QuizEvaluationRow
from guidami_ai_patente_ingestor.cli.models.evaluation import CoverageReport
from guidami_ai_patente_ingestor.configs import EvaluationConfig

# Re-exported, not called from this module: `keyword_document_frequency`'s SQL haystack
# is the coverage-side half of FR-2's "identical fields" criterion, `matches_any_keyword`
# is the ranking-side half (`ranking_calculator.py`). Importing the same function object
# here pins that no second, drifting implementation gets added to this module later; see
# `test_ranking_calculator.py::test_hit_uses_same_matching_as_coverage`.
from .keyword_matching import matches_any_keyword

__all__ = ["CoverageCalculator", "matches_any_keyword"]

_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(question_text: str) -> list[str]:
    """Splits `question_text` into lowercase word lexemes for a `to_tsquery` argument."""
    return _WORD_PATTERN.findall(question_text.lower())


def _median_and_quartiles(scores: Sequence[float]) -> tuple[float, tuple[float, float]]:
    """Returns `(median, (q1, q3))`, `0.0` on an empty series."""
    if not scores:
        return 0.0, (0.0, 0.0)
    sorted_scores = sorted(scores)
    median = statistics.median(sorted_scores)
    if len(sorted_scores) < 2:
        return median, (median, median)
    quartiles = statistics.quantiles(sorted_scores, n=4, method="inclusive")
    return median, (quartiles[0], quartiles[2])


def _share_above(scores: Sequence[float], threshold: float) -> float:
    """Returns the share of `scores` strictly above `threshold`, `0.0` on empty input."""
    if not scores:
        return 0.0
    return sum(1 for score in scores if score > threshold) / len(scores)


class CoverageCalculator:
    """Computes FR-2's two coverage views: a continuous text score, a keyword DF band."""

    def __init__(self, config: EvaluationConfig, repository: CorpusReadRepository) -> None:
        """Injects the run config (thresholds, DF cutoffs) and the corpus repository."""
        self._config = config
        self._repository = repository

    def text_score(self, question_text: str) -> float:
        """Continuous best-`ts_rank` score for `question_text`; no threshold is applied.

        Requires no `exact_keywords`. Delegates to `CorpusReadRepository.best_text_rank`,
        which scans the whole corpus, not only the retrieved top-k.
        """
        return self._repository.best_text_rank(_tokenize(question_text))

    def keyword_best_document_frequency(self, keywords: list[str] | None) -> int | None:
        """Returns the most selective (lowest) document frequency among `keywords`.

        `None`/empty `keywords` is a programming error: the caller must route those
        questions to the `not_measurable` bucket before calling this. Returns `None` when
        every keyword has DF `0` (matches nothing anywhere in the corpus — a lower
        bound, not a count); otherwise returns the minimum DF among keywords with DF >= 1.
        """
        if not keywords:
            raise ValueError(
                "keywords must be a non-empty list; route None/empty exact_keywords to "
                "the not_measurable bucket before calling keyword_best_document_frequency"
            )
        document_frequencies = [
            self._repository.keyword_document_frequency(keyword) for keyword in keywords
        ]
        matching = [df for df in document_frequencies if df >= 1]
        return min(matching) if matching else None

    def build_report(
        self,
        rows: Sequence[QuizEvaluationRow],
        scores: Sequence[float],
        best_dfs: Sequence[int | None],
    ) -> CoverageReport:
        """Aggregates per-question scores and keyword DFs into FR-2's coverage bands.

        `not_measurable` is derived from `row.exact_keywords` directly, not from
        `best_dfs`: `best_dfs[i]` is only meaningful when the corresponding row is
        keyword-measurable (the caller must not have called
        `keyword_best_document_frequency` for a non-measurable row, but whatever
        placeholder it passes at that position is ignored here). `by_topic` reports the
        same bands one level deep — a per-topic report's own `by_topic` is empty.
        """
        return self._build_report(rows, scores, best_dfs, include_topics=True)

    def _build_report(
        self,
        rows: Sequence[QuizEvaluationRow],
        scores: Sequence[float],
        best_dfs: Sequence[int | None],
        include_topics: bool,
    ) -> CoverageReport:
        text_median, text_quartiles = _median_and_quartiles(scores)
        text_share_above = {
            threshold: _share_above(scores, threshold)
            for threshold in self._config.text_coverage_thresholds
        }
        measurable_dfs = [df for row, df in zip(rows, best_dfs, strict=True) if row.exact_keywords]
        not_measurable = sum(1 for row in rows if not row.exact_keywords)
        keyword_matches_nothing = sum(1 for df in measurable_dfs if df is None)
        keyword_band = {
            cutoff: sum(1 for df in measurable_dfs if df is not None and df > cutoff)
            for cutoff in self._config.keyword_df_cutoffs
        }
        by_topic: dict[str, CoverageReport] = {}
        if include_topics:
            for topic in dict.fromkeys(row.topic for row in rows):
                by_topic[topic] = self._build_report(
                    [row for row in rows if row.topic == topic],
                    [score for row, score in zip(rows, scores, strict=True) if row.topic == topic],
                    [df for row, df in zip(rows, best_dfs, strict=True) if row.topic == topic],
                    include_topics=False,
                )
        return CoverageReport(
            text_score_median=text_median,
            text_score_quartiles=text_quartiles,
            text_share_above=text_share_above,
            keyword_matches_nothing=keyword_matches_nothing,
            keyword_band=keyword_band,
            not_measurable=not_measurable,
            by_topic=by_topic,
        )
