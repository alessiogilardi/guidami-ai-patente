"""Deletes the labelings computed against an image description that is about to change."""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.quiz import QuizImageEntity
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import QuizLabelingInvalidationRepository

logger = logging.getLogger(__name__)


class InvalidateStaleLabelingsStep(Step):
    """Invalidates non-validated labelings of questions whose image description changed.

    The labeling configuration epoch does not cover the image description, so without
    this step a regenerated description would silently leave every labeling of an image
    question computed against the old text. Enforced at the write point (spec 0023,
    AD-3), right before `StoreQuizStep`: if the store then fails, the only effect is
    labelings that get recomputed on demand. Human-validated labelings are never deleted.
    """

    def __init__(self, name: str, repository: QuizLabelingInvalidationRepository) -> None:
        """Injects the step name and the invalidation repository."""
        super().__init__(name)
        self._repository = repository

    def execute(self, context: FlowContext) -> None:
        """Compares incoming descriptions with the stored ones and deletes stale labelings."""
        images = cast(list[QuizImageEntity], context.get(context_keys.QUIZ_IMAGE_ENTITIES))
        incoming = {image.filename: image.description for image in images}
        stored = self._repository.find_descriptions(list(incoming))
        changed = [
            filename
            for filename, description in incoming.items()
            if stored.get(filename) != description
        ]
        if not changed:
            logger.debug("No image description changed; no labeling to invalidate")
        else:
            self._invalidate(changed)

    def _invalidate(self, changed: list[str]) -> None:
        validated = self._repository.count_validated_labelings(changed)
        if validated:
            logger.warning(
                "Keeping %d human-validated labeling(s) computed against a changed image "
                "description",
                validated,
            )
        deleted = self._repository.delete_unvalidated_labelings(changed)
        logger.info(
            "Invalidated %d labeling(s) across %d image(s) with a changed description",
            deleted,
            len(changed),
        )

    def get_required_keys(self) -> set[str]:
        """Requires `QUIZ_IMAGE_ENTITIES`."""
        return {context_keys.QUIZ_IMAGE_ENTITIES}

    def get_produced_keys(self) -> set[str]:
        """No produced key: the step only has a side effect on the database."""
        return set()
