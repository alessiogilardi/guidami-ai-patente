from collections.abc import Sequence


def require_canonical_lexeme_fields(fields: Sequence[str]) -> None:
    """Raises unless `fields` is non-empty and sorted.

    One implementation shared by `LabelingRunEntity` and `LabelingEpoch` (D8): both
    enforce the same invariant, and `labeling_runs.lexeme_fields` is compared as a
    whole array by FR-8's precedence query, so order is semantic. Distinct from
    `LabelingConfig._validate_lexeme_fields`, which enforces a different rule
    (no duplicates) and is deliberately left alone.
    """
    if not fields:
        raise ValueError("lexeme_fields must name at least one field")
    if list(fields) != sorted(fields):
        raise ValueError(f"lexeme_fields must be sorted, got {tuple(fields)}")
