"""Selects the enriched quizzes whose image description is to be regenerated."""

import logging
from collections.abc import Collection
from typing import cast

from flowstep import FlowContext, Step

from guidami_ai_patente_ingestor.exceptions import UnknownImageError
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)


class FilterByImageStep(Step):
    """Keeps the quizzes that use an image, optionally restricted to named images.

    Selection is by *image*, not by question: every quiz that uses a selected image is
    kept, so the describer's per-image context is never partial. Quizzes without an
    image are always dropped (there is nothing to rewrite for them).

    Args:
        name: Unique step name within the flow.
        input_key: ``FlowContext`` key to read the full enriched quiz list from.
        output_key: ``FlowContext`` key to write the selected quizzes to.
        images: Image filenames to keep; empty means every image in use.
    """

    def __init__(
        self, name: str, input_key: str, output_key: str, images: Collection[str]
    ) -> None:
        """Injects the step name, the context keys and the requested image filenames."""
        super().__init__(name)
        self._input_key = input_key
        self._output_key = output_key
        self._images = frozenset(images)

    def execute(self, context: FlowContext) -> None:
        """Selects the quizzes of the requested images.

        Raises:
            UnknownImageError: if a requested filename is used by no quiz.
        """
        quizzes = cast(list[EnrichedQuizModel], context.get(self._input_key))
        used = {quiz.image for quiz in quizzes if quiz.image}
        unknown = sorted(self._images - used)
        if unknown:
            raise UnknownImageError(unknown)

        selected = [
            quiz
            for quiz in quizzes
            if quiz.image and (not self._images or quiz.image in self._images)
        ]
        logger.info(
            "Selected %d quizzes across %d image(s) for description regeneration",
            len(selected),
            len({quiz.image for quiz in selected}),
        )
        context.put(self._output_key, selected)

    def get_required_keys(self) -> set[str]:
        """Requires ``input_key`` in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produces ``output_key``."""
        return {self._output_key}
