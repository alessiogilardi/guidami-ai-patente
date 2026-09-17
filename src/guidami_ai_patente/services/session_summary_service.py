"""Backs GET /quiz-answers/summary (spec 0016, FR-9, AD-16)."""

import asyncio

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.models import SessionSummary, SessionSummaryRequest
from guidami_ai_patente.repositories import QuizAnswerRepository


@service
class SessionSummaryService(AsyncUseCase[SessionSummaryRequest, SessionSummary]):
    """Thin `AsyncUseCase` wrapper: the aggregation itself lives in SQL (AD-16).

    `AsyncUseCase` rather than `UseCase`, unlike every existing service in this
    package: this is a brand-new class with no existing synchronous caller to stay
    consistent with (see this plan's Global Constraints deferred-migration note) —
    new services are written this way going forward, crossing into the sync
    repository layer with `asyncio.to_thread` themselves instead of leaving that to
    the router. `QuizAnswerRepository.session_summary` itself stays synchronous
    (AD-10); only the boundary-crossing point moves.
    """

    answers: Autowired[QuizAnswerRepository]

    async def execute(self, request: SessionSummaryRequest) -> SessionSummary:
        """Returns the session's answered/correct counts, scoped to the caller."""
        return await asyncio.to_thread(
            self.answers.session_summary, request.telegram_user_id, request.session_id
        )
