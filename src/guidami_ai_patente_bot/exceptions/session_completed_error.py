"""Raised when a chat's session has no further question to propose."""


class SessionCompletedError(Exception):
    """The session ran out of questions (topic exhausted or review queue empty, AD-7)."""
