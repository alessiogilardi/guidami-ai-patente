"""Raised when a call to the guidami-ai-patente HTTP API fails."""


class QuizApiError(Exception):
    """A non-2xx response, timeout or connection error from the API (FR-5)."""
