"""Domain-level invariant checks shared across entities (and, later, `labeling/`)."""

from .lexeme_fields import require_canonical_lexeme_fields

__all__ = ["require_canonical_lexeme_fields"]
