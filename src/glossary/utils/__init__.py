"""Generic helpers of the glossary package, with no domain-specific logic."""

from .chunking import split_into_chunks
from .entry_markers import count_expected_entries, is_abrogated, is_cross_reference

__all__ = ["count_expected_entries", "is_abrogated", "is_cross_reference", "split_into_chunks"]
