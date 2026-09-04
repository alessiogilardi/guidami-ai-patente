import asyncio
import logging
import random
from collections.abc import Sequence

from commons.repositories.db import QuizReadRepository
from commons.use_cases import AsyncUseCase
from domain.models.retrieval import QuizEvaluationRow
from labeling.constants import EMBEDDING_MODEL_COLUMN
from labeling.models import QuestionLabelingRequest

from .question_labeling_service import QuestionLabelingService

logger = logging.getLogger(__name__)


class GoldenSetLabelingService(AsyncUseCase[int, int]):
    """Fans the shared per-question labeling unit out over the quiz bank (FR-6, FR-10).

    Selects which questions to label — `topics` first, then `question_limit` (FR-18) —
    and runs `QuestionLabelingService` over them concurrently, bounded by a semaphore
    built inside `execute` rather than on `self` (a semaphore binds to the event loop
    of its first use).

    The judging itself lives in `QuestionLabelingService`, shared with the API's live
    cache fill, because the epoch key cannot tell two judging implementations apart
    (AD-12). What is left here is selection and concurrency.

    Any failure propagates and aborts the whole run (PD-9): `asyncio.gather` is never
    called with `return_exceptions=True`, so an incomplete run cannot look complete.

    `topics`, when given, restricts *which* questions are labeled (FR-18) — applied
    before `question_limit`, so `--limit N --topic t` means "N questions of topic t".
    It never reaches `labeling_runs` and is not part of the configuration epoch.
    """

    def __init__(
        self,
        candidate_variant: str,
        shuffle_seed: int,
        max_concurrency: int,
        question_limit: int | None,
        topics: Sequence[str] | None,
        quiz_repository: QuizReadRepository,
        question_labeling_service: QuestionLabelingService,
    ) -> None:
        """Injects the selection parameters and the read/labeling collaborators."""
        self._candidate_variant = candidate_variant
        self._shuffle_seed = shuffle_seed
        self._max_concurrency = max_concurrency
        self._question_limit = question_limit
        self._topics = frozenset(topics) if topics else None
        self._quiz_repository = quiz_repository
        self._question_labeling_service = question_labeling_service

    async def execute(self, request: int) -> int:
        """Labels every selected question under run id `request`.

        Returns:
            The number of questions labeled (before any labeling could fail).
        """
        rows = self._quiz_repository.fetch_with_vectors(
            self._candidate_variant, EMBEDDING_MODEL_COLUMN
        )
        if self._topics is not None:
            # Filters before the limit, so `--limit N --topic t` means "N questions
            # of t", not "the first N of the bank, of which some are t" (FR-18).
            rows = [row for row in rows if row.topic in self._topics]
        if self._question_limit is not None:
            shuffled = list(rows)
            random.Random(f"limit:{self._shuffle_seed}").shuffle(shuffled)
            rows = shuffled[: self._question_limit]

        logger.info("Labeling %d question(s) under run %d", len(rows), request)
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        await asyncio.gather(*(self._label_one(row, request, semaphore) for row in rows))
        return len(rows)

    async def _label_one(
        self, row: QuizEvaluationRow, run_id: int, semaphore: asyncio.Semaphore
    ) -> None:
        async with semaphore:
            labeling_id = await self._question_labeling_service(
                QuestionLabelingRequest(row=row, resolve_run_id=lambda: run_id)
            )
            if labeling_id is None:
                # D6: `insert_run` just created this run_id and each question is visited
                # once, so a conflict is a defect, not a race. It is a `warning`, and
                # the discarded write is NOT counted as a labeling. The API caller
                # treats the same `None` as the designed outcome of AD-19.
                logger.warning(
                    "Unexpected: labeling for quiz %s already existed under batch "
                    "run %d, write discarded",
                    row.number,
                    run_id,
                )
