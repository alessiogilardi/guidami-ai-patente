"""Raised when the backend rejects a call with 403 (spec 0016, FR-10)."""

from .quiz_api_error import QuizApiError


class UnauthorizedError(QuizApiError):
    """The caller's `telegram_user_id` is not yet approved (backend `403`).

    A distinct subtype of `QuizApiError` rather than a new top-level exception, so
    code that only needs "did the API call fail" keeps catching `QuizApiError` — only
    `handle_error` (Task 8) needs to tell this case apart, for its friendlier message.
    """
