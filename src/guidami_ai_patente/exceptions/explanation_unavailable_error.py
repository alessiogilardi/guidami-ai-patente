"""Raised when the explanation could not be produced for a transient reason."""

from .guidami_api_error import GuidamiApiError


class ExplanationUnavailableError(GuidamiApiError):
    """The judge, the writer or the provider failed; the corpus is not the problem.

    A `503` (FR-13, AD-20). Kept rigorously distinct from `insufficient_knowledge`:
    that answer is a statement about the law, and a provider timeout is not evidence
    of one. It carries no `reason` from FR-7's vocabulary, precisely so a client cannot
    mistake one for the other.

    Covers a timeout against the request-wide deadline, a rate limit surviving the
    transport retries, and a writer response that still cites an ordinal outside the
    supplied commas after its retries (FR-10).
    """
