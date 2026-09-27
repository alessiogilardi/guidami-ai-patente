"""Normalizes a glossary term's display casing to sentence case."""


def normalize_term_casing(term: str) -> str:
    """Renders `term` as sentence case: lowercased, then its first letter capitalized.

    DB-sourced terms are stored ALL CAPS by the build pipeline's own `normalize_term`
    (`src/glossary/utils/normalization.py`), while `GlossaryEnricherAgent`'s live terms
    preserve whatever casing the quiz question itself used — mixing both verbatim in
    the same `translation_hints` list looks inconsistent to the end user. Lowercasing
    the whole term first (rather than leaving the tail untouched, as `capitalize_
    definition` does for definitions) is what actually fixes the ALL CAPS case; the
    trade-off is that an acronym embedded inside a term (e.g. "ABS") loses its internal
    capitals, accepted as strictly better than the pre-existing mixed-casing bug.
    """
    stripped = term.strip().lower()
    return stripped[:1].upper() + stripped[1:]
