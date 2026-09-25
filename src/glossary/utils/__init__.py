"""Generic helpers of the glossary package, with no domain-specific logic."""

from .chunking import split_into_chunks
from .entry_markers import count_expected_entries, is_abrogated, is_cross_reference
from .normalization import capitalize_definition, normalize_term

__all__ = [
    "capitalize_definition",
    "count_expected_entries",
    "is_abrogated",
    "is_cross_reference",
    "normalize_term",
    "split_into_chunks",
]
