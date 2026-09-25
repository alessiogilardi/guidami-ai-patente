"""Mechanical detection of a definitions block's own entry markers (AD-10).

Shared by chunking (where to cut) and by the extractor's completeness check (how many
entries a chunk must yield). Never extracts a term or definition itself.
"""

import re

# CdS art. 3's own marker: "...significati: 1) AREA DI INTERSEZIONE: ... 2) Area
# pedonale: ...", preceded by ". " (end of the previous entry), ": " (end of the
# block's preamble) or the start of the text.
NUMERIC_MARKER = re.compile(r"(?:(?<=\. )|(?<=: )|^)\d+(?:-bis|-ter)?\)\s+(?=[A-ZÀÈÉÌÒÙ])")

# CAP art. 1's own marker: "...si intendono per: a) termine: definizione; b) termine:
# definizione; ...", preceded by "; " (end of the previous entry), ": " (end of the
# block's preamble) or the start of the text.
ALPHA_MARKER = re.compile(r"(?:(?<=; )|(?<=: )|^)[a-z]{1,3}\)\s")

MARKERS = (NUMERIC_MARKER, ALPHA_MARKER)

# The corpus' own repeal wording: "NUMERO ABROGATO DALLA L. ...", "LETTERA ABROGATA
# DAL D.LGS. ...". Uppercase only, so an ordinary definition mentioning an abrogated
# rule in running text is never mistaken for a repealed entry.
_ABROGATION_PATTERN = re.compile(r"\bABROGAT[OA]\b")
_CROSS_REFERENCE_PATTERN = re.compile(r"cfr\.", re.IGNORECASE)


def is_abrogated(text: str) -> bool:
    """True when `text` carries the corpus' own repeal marker."""
    return _ABROGATION_PATTERN.search(text) is not None


def is_cross_reference(definition: str) -> bool:
    """True when `definition` is only a pointer to another entry ("cfr. TERMINE")."""
    return _CROSS_REFERENCE_PATTERN.match(definition.strip()) is not None


def count_expected_entries(text: str) -> int:
    """Returns a lower bound on the definitional entries `text` contains.

    Uses whichever marker matches most often (so a CAP block's nested numeric
    sub-items never outvote its lettered entries), and discounts repealed entries,
    cross-reference-only entries and segments with no "term: definition" colon.
    A lower bound, not an exact count: an entry whose marker the patterns miss is
    simply not expected.
    """
    starts = max(([m.start() for m in marker.finditer(text)] for marker in MARKERS), key=len)
    if not starts:
        return 0
    ends = [*starts[1:], len(text)]
    return sum(
        1 for start, end in zip(starts, ends, strict=True) if _is_definitional(text[start:end])
    )


def _is_definitional(segment: str) -> bool:
    _, colon, definition = segment.partition(":")
    return bool(colon) and not is_abrogated(segment) and not is_cross_reference(definition)
