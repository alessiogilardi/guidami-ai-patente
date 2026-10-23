"""Backs GET /quiz-questions/review/next (FR-4)."""

import asyncio
import hashlib
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import (
    AnsweredQuestion,
    QuestionMastery,
    QuizQuestionSummary,
    ReviewRequest,
)
from guidami_ai_patente.repositories import QuizAnswerRepository, QuizQuestionRepository

from .mastery_calculator import MasteryCalculator

logger = logging.getLogger(__name__)


@service
class ReviewQuestionService(AsyncUseCase[ReviewRequest, QuizQuestionSummary | None]):
    """Picks the next in-review question for a user within a session.

    Crosses into the synchronous repositories with `asyncio.to_thread` itself, so the
    router just awaits it. Selection is a pure function of the stored history and the
    `session_id`: no server-side session state.
    """

    answers: Autowired[QuizAnswerRepository]
    questions: Autowired[QuizQuestionRepository]
    mastery: Autowired[MasteryCalculator]
    config: Autowired[AppConfig]

    async def execute(self, request: ReviewRequest) -> QuizQuestionSummary | None:
        """Returns the next question to review, or `None` when nothing is due.

        Args:
            request: The caller's Telegram user id and the current session id.

        Returns:
            The question in the `/random` projection, or `None`.
        """
        history = await asyncio.to_thread(self.answers.user_history, request.telegram_user_id)
        number = self._pick(history, request.session_id)
        logger.debug(
            "Review pick (history_size=%d, chosen=%s)",
            len(history),
            number,
        )
        if number is None:
            return None
        return await asyncio.to_thread(self.questions.find_by_number, number)

    def _pick(self, history: list[AnsweredQuestion], session_id: str) -> str | None:
        states = self.mastery.question_states(history)
        in_session = {a.number for a in history if a.session_id == session_id}
        unseen = [s for s in states.values() if s.in_review and s.number not in in_session]
        if unseen:
            logger.debug("Review pass: unseen in-review (candidates=%d)", len(unseen))
            return min(unseen, key=lambda s: self._unseen_key(s, session_id)).number
        logger.debug("Review pass: re-ask (no unseen in-review questions left)")
        return self._oldest_reask(history, session_id)

    @staticmethod
    def _unseen_key(state: QuestionMastery, session_id: str) -> tuple[int, int, str]:
        tiebreak = hashlib.md5((session_id + state.number).encode()).hexdigest()  # noqa: S324
        return (state.streak, -state.wrong_count, tiebreak)

    def _oldest_reask(self, history: list[AnsweredQuestion], session_id: str) -> str | None:
        counts: dict[str, int] = {}
        last_position: dict[str, int] = {}
        last_correct: dict[str, bool] = {}
        for position, answer in enumerate(history):
            if answer.session_id == session_id:
                counts[answer.number] = counts.get(answer.number, 0) + 1
                last_position[answer.number] = position
                last_correct[answer.number] = answer.is_correct
        limit = self.config.review_max_repeats_per_session
        due = [
            number
            for number, correct in last_correct.items()
            if not correct and counts[number] <= limit
        ]
        if not due:
            return None
        return min(due, key=lambda number: last_position[number])
