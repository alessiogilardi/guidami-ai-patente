from collections.abc import Sequence

from glossary.models import BlockOutcome


class GlossaryBuildError(RuntimeError):
    """Raised when one or more blocks failed during `build-glossary` (FR-7)."""

    def __init__(self, failed_labels: Sequence[str], outcomes: Sequence[BlockOutcome]) -> None:
        """Carries the failed blocks' labels alongside every block that did complete."""
        super().__init__(f"{len(failed_labels)} block(s) failed: {', '.join(failed_labels)}")
        self.failed_labels = tuple(failed_labels)
        self.outcomes = tuple(outcomes)


class GlossaryTranslationError(RuntimeError):
    """Raised when one or more batches failed during `translate-glossary-terms` (FR-5)."""

    def __init__(self, failed_ids: Sequence[int]) -> None:
        """Carries the ids of every `glossary_entries` row whose translation batch failed."""
        super().__init__(f"{len(failed_ids)} term(s) failed to translate: {list(failed_ids)}")
        self.failed_ids = tuple(failed_ids)


class GlossaryDefinitionSimplificationError(RuntimeError):
    """Raised when one or more batches failed during `simplify-glossary-definitions`."""

    def __init__(self, failed_ids: Sequence[int]) -> None:
        """Carries the ids of every `glossary_entries` row whose simplification batch failed."""
        super().__init__(f"{len(failed_ids)} definition(s) failed to simplify: {list(failed_ids)}")
        self.failed_ids = tuple(failed_ids)
