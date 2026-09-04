"""Outcome of an explanation request, in a closed two-value vocabulary."""

from enum import StrEnum, auto


class ExplanationResult(StrEnum):
    """Whether the endpoint explained the answer or reported a corpus gap (FR-5, FR-7).

    Deliberately two members. A third value for a transient failure was rejected
    (AD-20): hiding a server-side outage behind a `200` would let a client that only
    branches on the HTTP status treat it as an answer, so an outage is FR-13's `503`
    and never appears here.

    `INSUFFICIENT_KNOWLEDGE` is always accompanied by an `InsufficientKnowledgeReason`,
    which is what separates a **pipeline** gap (`not_indexed`, fixed by re-running
    ingestion) from a **corpus** gap no re-run fixes (AD-6).
    """

    EXPLAINED = auto()
    INSUFFICIENT_KNOWLEDGE = auto()
