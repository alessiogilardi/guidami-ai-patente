"""Whether `exact_keywords` carry signal about the corpus (FR-10)."""

import statistics
from collections.abc import Sequence

from commons.repositories.db import CorpusReadRepository


class KeywordQualityCalculator:
    """Computes FR-10's direct keyword-quality measures and their adherence association."""

    def __init__(self, repository: CorpusReadRepository) -> None:
        """Injects the corpus repository used for document-frequency lookups."""
        self._repository = repository

    def zero_match_share(self, distinct_keywords: Sequence[str]) -> float:
        """Share of `distinct_keywords` matching no comma anywhere in the corpus."""
        if not distinct_keywords:
            return 0.0
        zero_match_count = sum(
            1
            for keyword in distinct_keywords
            if self._repository.keyword_document_frequency(keyword) == 0
        )
        return zero_match_count / len(distinct_keywords)

    def document_frequency_distribution(self, distinct_keywords: Sequence[str]) -> dict[str, int]:
        """Document frequency of each of `distinct_keywords`, for the FR-10 distribution."""
        return {
            keyword: self._repository.keyword_document_frequency(keyword)
            for keyword in distinct_keywords
        }

    def hit_adherence_association(
        self, hits: Sequence[bool], adherences: Sequence[float]
    ) -> float:
        """Point-biserial correlation between `hits` and `adherences` (FR-10).

        Returns `nan` when either series has zero variance, never `0.0`, so a
        degenerate input stays distinguishable from a genuine null association.
        """
        try:
            return statistics.correlation([float(hit) for hit in hits], list(adherences))
        except statistics.StatisticsError:
            return float("nan")
