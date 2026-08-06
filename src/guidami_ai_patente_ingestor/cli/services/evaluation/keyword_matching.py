"""Single shared definition of "does a keyword match a comma" (FR-2's identical-fields criterion).

FR-2 requires the coverage test and the ranking hit test to search exactly the same
fields, but they necessarily do so through two different engines: coverage matches in
SQL (`CorpusReadRepository.keyword_document_frequency`,
`(a.title || ' ' || c.text) ILIKE %s`), ranking matches in Python
(`RankingCalculator.is_hit`). They therefore cannot share a call site -- only a
definition. This module is that definition; `corpus_haystack` mirrors the SQL
concatenation exactly, and both `coverage_calculator` and `ranking_calculator` import
`matches_any_keyword` from here rather than each defining their own copy.
"""

from collections.abc import Sequence


def corpus_haystack(article_title: str, text: str) -> str:
    """Builds the searchable text for one comma: article title + comma text.

    Mirrors `CorpusReadRepository`'s SQL concatenation `a.title || ' ' || c.text`
    exactly (verified by a cross-engine integration test in `test_corpus_read_repository.py`).
    """
    return f"{article_title} {text}"


def matches_any_keyword(keywords: Sequence[str], haystack: str) -> bool:
    """True if any of `keywords` appears case-insensitively anywhere in `haystack`."""
    lowered_haystack = haystack.lower()
    return any(keyword.lower() in lowered_haystack for keyword in keywords)
