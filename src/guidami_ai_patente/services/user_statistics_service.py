"""Backs GET /quiz-answers/statistics (FR-3)."""

import asyncio

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.models import UserStatistics
from guidami_ai_patente.repositories import QuizAnswerRepository, QuizQuestionRepository

from .mastery_calculator import MasteryCalculator


@service
class UserStatisticsService(AsyncUseCase[int, UserStatistics]):
    """Combines a user's answer history with the bank's topics into mastery statistics.

    Crosses into the synchronous repositories with `asyncio.to_thread` itself, like
    `SessionSummaryService`, so the router just awaits it.
    """

    answers: Autowired[QuizAnswerRepository]
    questions: Autowired[QuizQuestionRepository]
    mastery: Autowired[MasteryCalculator]

    async def execute(self, request: int) -> UserStatistics:
        """Computes the statistics of the given Telegram user.

        Args:
            request: The caller's Telegram user id.

        Returns:
            Totals, mastered/in-review counts and the ranked per-topic breakdown.
        """
        history = await asyncio.to_thread(self.answers.user_history, request)
        topic_totals = await asyncio.to_thread(self.questions.list_topics)
        states = self.mastery.question_states(history)
        in_review = sum(1 for state in states.values() if state.in_review)
        return UserStatistics(
            answered=len(history),
            seen=len(states),
            bank_total=sum(topic.question_count for topic in topic_totals),
            mastered=len(states) - in_review,
            in_review=in_review,
            topics=self.mastery.topic_mastery(states, topic_totals),
        )
