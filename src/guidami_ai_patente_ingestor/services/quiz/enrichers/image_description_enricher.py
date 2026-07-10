import logging
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from commons.use_cases import UseCase
from commons.utils import deduplicate
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import RoadSignDescriberResponse
from guidami_ai_patente_ingestor.mappers.agents import RoadSignDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)

_DedupeKey = tuple[str, str, str]  # (image, topic, text)


def _make_key(q: EnrichedQuizModel) -> _DedupeKey:
    return (cast(str, q.image), q.topic, q.text)


class ImageDescriptionEnricher(UseCase[Iterable[EnrichedQuizModel], list[EnrichedQuizModel]]):
    """Enriches sub-questions with the road sign description.

    The dedup key is `(image, topic, text)`: the same image in different contexts
    triggers separate calls to get contextualized descriptions; exact duplicates
    are collapsed.
    """

    def __init__(self, road_sign_describer: RoadSignDescriberAgent) -> None:
        """Inject the road sign describer agent."""
        self._road_sign_describer = road_sign_describer

    def execute(self, request: Iterable[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Enrich each quiz item with a road sign description where an image is present."""
        questions = list(request)
        descriptions = self._build_description_map(questions)
        return [self._apply_description(q, descriptions) for q in questions]

    def _apply_description(
        self, q: EnrichedQuizModel, descriptions: dict[_DedupeKey, RoadSignDescriberResponse]
    ) -> EnrichedQuizModel:
        if not q.image:
            return q
        response = descriptions.get(_make_key(q))
        if response is None:
            return q
        return RoadSignDescriberMapper.from_response_to_enriched_quiz(q, response)

    def _build_description_map(
        self, questions: list[EnrichedQuizModel]
    ) -> dict[_DedupeKey, RoadSignDescriberResponse]:
        unique = deduplicate(
            (q for q in questions if q.image is not None),
            key=_make_key,
        )
        return {
            _make_key(q): desc for q in unique if (desc := self._describe_image(q)) is not None
        }

    def _describe_image(self, q: EnrichedQuizModel) -> RoadSignDescriberResponse | None:
        image = cast(str, q.image)
        req = RoadSignDescriberMapper.from_enriched_quiz_to_request(q)
        try:
            return self._road_sign_describer.run_sync(req, images=(Path(image),))
        except (FileNotFoundError, PermissionError):
            logger.warning("Image file not found or inaccessible, skipping: %s", image)
            return None
        except Exception:
            # TODO: narrow this broad catch once the agent domain-exception hierarchy
            # lands (see the deferred EmbeddingError plan); it currently also swallows
            # real bugs. Per-item degrade is intentional: one bad image must not kill
            # the batch.
            logger.warning("Failed to describe image, skipping: %s", image, exc_info=True)
            return None
