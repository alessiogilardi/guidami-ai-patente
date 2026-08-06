"""Lexical adherence, dense/FTS agreement and distance margin (FR-5, FR-6)."""

import re
from collections.abc import Sequence

from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import RetrievedComma
from guidami_ai_patente_ingestor.configs import EvaluationConfig

_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


class AdherenceCalculator:
    """Computes FR-5's lexical adherence and FR-6's dense/FTS agreement signals."""

    def __init__(self, config: EvaluationConfig, repository: CorpusReadRepository) -> None:
        """Injects the run config (`k_values`, for `distance_margin`'s fixed depth)."""
        self._config = config
        self._repository = repository

    def build_tsquery(self, question_text: str) -> list[str]:
        """Splits `question_text` into lexemes, to be OR-joined by the repository (AD-3).

        Must never delegate to Postgres's AND-joining query-string builders (measured
        to return 0.0000 on every row of a sample, AD-3) — only plain lexeme splitting,
        OR-joined downstream, discriminates.
        """
        return _WORD_PATTERN.findall(question_text.lower())

    def top1_adherence(self, lexemes: list[str], retrieved: Sequence[RetrievedComma]) -> float:
        """Weighted `ts_rank` of the top-1 retrieved comma against `lexemes`."""
        if not retrieved:
            return 0.0
        top = retrieved[0]
        weighted, _title_only, _text_only = self._repository.rank_text(
            lexemes, top.article_title, top.text
        )
        return weighted

    def dense_fts_overlap(
        self, dense: Sequence[RetrievedComma], fts: Sequence[RetrievedComma]
    ) -> float:
        """Share of `dense`'s top-k set also present in `fts`'s top-k set (FR-6)."""
        if not dense or not fts:
            return 0.0
        dense_citations = {comma.citation for comma in dense}
        fts_citations = {comma.citation for comma in fts}
        return len(dense_citations & fts_citations) / len(dense_citations)

    def distance_margin(self, retrieved: Sequence[RetrievedComma]) -> float:
        """Difference between the top-1 and the deepest-configured-`k` cosine distance.

        The margin is defined against one fixed depth (`max(config.k_values)`), per
        FR-6, rather than an ambiguous "top-k".
        """
        depth = max(self._config.k_values)
        window = retrieved[:depth]
        if len(window) < 2:
            return 0.0
        return window[-1].distance - window[0].distance
