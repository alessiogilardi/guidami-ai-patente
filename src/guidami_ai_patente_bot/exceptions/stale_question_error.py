"""Raised when a callback references a question no longer current in its chat."""


class StaleQuestionError(Exception):
    """A button tap named `number`, but the chat has since moved on (FR-3)."""

    def __init__(self, number: str) -> None:
        """Records the stale question `number` referenced by the button tap."""
        super().__init__(f"question {number} is no longer the chat's current question")
        self.number = number
