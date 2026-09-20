"""Ensures a question's comma labeling exists, under its own deadline (spec 0017)."""

import asyncio
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.exceptions import ExplanationUnavailableError, QuestionNotFoundError
from guidami_ai_patente.models import CommaSelection
from guidami_ai_patente.repositories import QuizQuestionRepository

from .comma_selector_service import CommaSelectorService

logger = logging.getLogger(__name__)


@service
class LabelingService(AsyncUseCase[str, CommaSelection]):
    """Ensures a current comma labeling exists for a question (FR-4, AD-2, AD-10).

    Wraps `CommaSelectorService` with two things it does not do itself: the
    request-wide deadline that used to live on `ExplanationService` before
    retrieval and the judge moved here (AD-1, AD-10), and the existence check
    `/check` and `/explanation` both already perform — `CommaSelectorService`
    on its own would silently 204 for an unknown question, which would be the
    one endpoint of the three behaving differently for a typo'd number.
    `find_correct_answer` is the same cheap existence probe `QuizAnswerChecker`
    already uses for the identical purpose.

    `asyncio.timeout` only bounds `await`ed work, not code already running inside
    `asyncio.to_thread`: an executor thread cannot be interrupted, so a cancellation
    only lands once that thread call returns (see `ExplanationService`'s docstring
    for the fuller explanation — same deliberate design, not a bug). It is arguably
    more load-bearing here than there: `execute` wraps `selector`
    (`CommaSelectorService`), whose own path is mostly threaded SQL (retrieval,
    golden-set reads/writes) plus a single awaited judge call, so most of the wall
    clock this deadline is meant to bound is exactly the part it cannot cancel.
    """

    config: Autowired[AppConfig]
    questions: Autowired[QuizQuestionRepository]
    selector: Autowired[CommaSelectorService]

    async def execute(self, number: str) -> CommaSelection:
        """Ensures `number` is labeled, computing it live if needed.

        Args:
            number: The question's `number`.

        Raises:
            QuestionNotFoundError: No question carries `number` (404).
            ExplanationUnavailableError: The judge failed, or the request exceeded
                its deadline (503).
        """
        stored_answer = await asyncio.to_thread(self.questions.find_correct_answer, number)
        if stored_answer is None:
            raise QuestionNotFoundError(number)

        try:
            async with asyncio.timeout(self.config.labeling_deadline_s):
                return await self.selector(number)
        except TimeoutError as error:
            logger.warning(
                "Labeling for quiz %s exceeded its %.1fs budget",
                number,
                self.config.labeling_deadline_s,
            )
            raise ExplanationUnavailableError(
                f"labeling question {number} exceeded the "
                f"{self.config.labeling_deadline_s:.0f}s budget"
            ) from error
