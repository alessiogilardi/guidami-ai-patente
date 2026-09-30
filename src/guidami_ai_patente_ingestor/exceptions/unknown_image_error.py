from collections.abc import Sequence


class UnknownImageError(ValueError):
    """Raised when a requested image filename is used by no enriched quiz.

    Attributes:
        unknown: The unknown filenames, in the order they were reported.
    """

    def __init__(self, unknown: Sequence[str]) -> None:
        """Stores the unknown filenames and builds a message listing every one."""
        self.unknown = tuple(unknown)
        super().__init__(
            f"Unknown image(s), not used by any enriched quiz: {', '.join(self.unknown)}"
        )
