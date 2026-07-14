import asyncio
import logging
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.mappers.agents import RoadSignDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)


class ImageDescriptionEnricher(UseCase[Iterable[EnrichedQuizModel], list[EnrichedQuizModel]]):
    """Enriches sub-questions with a road sign description, one call per image.

    All quizzes that reference the same image are grouped and described in a single
    vision call (their contexts are concatenated in the request); the resulting
    description and full LLM output are applied to every quiz in the group. Quizzes
    without an image pass through untouched.
    """

    def __init__(self, max_concurrency: int, road_sign_describer: RoadSignDescriberAgent) -> None:
        """Inject the concurrency limit and the road sign describer agent.

        Args:
            max_concurrency: Maximum number of in-flight vision calls per run.
            road_sign_describer: Agent used to describe each grouped image.
        """
        # Store the limit, not the Semaphore: an asyncio.Semaphore binds to the loop of its
        # first use, and execute() spins a fresh loop per call (asyncio.run). Building it
        # per-run in _fetch_descriptions keeps the enricher reusable across runs/loops.
        self._max_concurrency = max_concurrency
        self._road_sign_describer = road_sign_describer

    def execute(self, request: Iterable[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Enrich each quiz item with a road sign description where an image is present."""
        quizzes = list(request)

        quizzes_by_image = self._group_by_image(quizzes)
        # execute stays sync (flowstep/UseCase contract); it owns the event loop.
        descriptions = asyncio.run(self._fetch_descriptions(quizzes_by_image))

        return [self._enrich_quiz(quiz, descriptions) for quiz in quizzes]

    def _group_by_image(
        self, quizzes: list[EnrichedQuizModel]
    ) -> dict[str, list[EnrichedQuizModel]]:
        groups: defaultdict[str, list[EnrichedQuizModel]] = defaultdict(list)
        for quiz in quizzes:
            if quiz.image:
                groups[quiz.image].append(quiz)
        return groups

    async def _fetch_descriptions(
        self, groups: dict[str, list[EnrichedQuizModel]]
    ) -> dict[str, RoadSignDescriberResponse]:
        # Compute every LLM input first (sync, pure), then fire the calls concurrently.
        requests = {
            image: RoadSignDescriberMapper.from_enriched_quizzes_to_request(quizzes)
            for image, quizzes in groups.items()
        }
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        images = list(requests)
        responses = await asyncio.gather(
            *(self._describe_image(image, requests[image], semaphore) for image in images)
        )
        # gather preserves input order -> lockstep zip, no index bookkeeping.
        return {
            image: response
            for image, response in zip(images, responses, strict=True)
            if response is not None
        }

    def _enrich_quiz(
        self, quiz: EnrichedQuizModel, descriptions: dict[str, RoadSignDescriberResponse]
    ) -> EnrichedQuizModel:
        if not quiz.image or quiz.image not in descriptions:
            return quiz

        return RoadSignDescriberMapper.from_response_to_enriched_quiz(
            quiz, descriptions[quiz.image]
        )

    async def _describe_image(
        self,
        image: str,
        request_dto: RoadSignDescriberRequest,
        semaphore: asyncio.Semaphore,
    ) -> RoadSignDescriberResponse | None:
        try:
            async with semaphore:
                return await self._road_sign_describer.run(request_dto, images=(Path(image),))
        except (FileNotFoundError, PermissionError):
            logger.warning("Image file not found or inaccessible, skipping: %s", image)
            return None
        except Exception:
            # TODO: narrow this broad catch once the agent domain-exception hierarchy
            # lands (see the deferred EmbeddingError plan); it currently also swallows
            # real bugs. Per-image degrade is intentional: one bad image must not kill
            # the batch.
            logger.warning("Failed to describe image, skipping: %s", image, exc_info=True)
            return None
