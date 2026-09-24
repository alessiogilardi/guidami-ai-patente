"""Mechanical chunk-boundary detection (AD-10).

Finds a block's own regular top-level enumeration marker and splits there — never
asks the model to locate a cut inside a wall of text. This module only detects
boundaries; it never extracts a term or definition itself (AD-10).
"""

import re

# CdS art. 3's own marker: "1) AREA DI INTERSEZIONE: ... 2) Area pedonale: ...",
# preceded by ". " (end of the previous entry) or the start of the text.
_NUMERIC_MARKER = re.compile(r"(?:(?<=\. )|^)\d+(?:-bis|-ter)?\)\s+(?=[A-ZÀÈÉÌÒÙ])")

# CAP art. 1's own marker: "a) termine: definizione; b) termine: definizione; ...",
# preceded by "; " or the start of the text — excludes nested "1) ... 2) ..."
# sub-items (those are preceded by ": ", never "; ").
_ALPHA_MARKER = re.compile(r"(?:(?<=; )|^)[a-z]{1,3}\)\s")

_MARKERS = (_NUMERIC_MARKER, _ALPHA_MARKER)


def split_into_chunks(text: str, max_chars: int) -> list[tuple[int, str]]:
    """Splits `text` into chunks of at most `max_chars`, each `(start_offset, chunk)`.

    Returns a single chunk covering the whole text when it already fits. Otherwise,
    splits at the block's own marker (packing consecutive entries up to the limit) if
    one is found with at least two matches; falls back to a raw character-count split
    when no marker is detected (AD-10).
    """
    if len(text) <= max_chars:
        return [(0, text)]

    boundaries = _find_boundaries(text)
    if boundaries is None:
        return _split_by_char_count(text, max_chars)

    return _pack_entries(text, boundaries, max_chars)


def _find_boundaries(text: str) -> list[int] | None:
    for marker in _MARKERS:
        positions = [match.start() for match in marker.finditer(text)]
        if len(positions) >= 2:
            return positions
    return None


def _pack_entries(text: str, boundaries: list[int], max_chars: int) -> list[tuple[int, str]]:
    """Greedily packs consecutive entries into chunks of at most `max_chars` each."""
    entry_starts = boundaries if boundaries[0] == 0 else [0, *boundaries]
    chunks: list[tuple[int, str]] = []
    chunk_start = entry_starts[0]
    pending_start = entry_starts[0]
    for entry_start in entry_starts[1:]:
        if entry_start - chunk_start > max_chars:
            chunks.append((chunk_start, text[chunk_start:pending_start]))
            chunk_start = pending_start
        pending_start = entry_start
    chunks.append((chunk_start, text[chunk_start:]))
    return chunks


def _split_by_char_count(text: str, max_chars: int) -> list[tuple[int, str]]:
    return [(start, text[start : start + max_chars]) for start in range(0, len(text), max_chars)]
