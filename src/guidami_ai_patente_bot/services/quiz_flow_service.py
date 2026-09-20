"""Sequences propose/answer calls against the API and derives the chat's session state."""

import uuid

from pywire import Autowired, service

from guidami_ai_patente_bot.clients import QuizApiClient
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus
from guidami_ai_patente_bot.exceptions import QuizApiError, StaleQuestionError
from guidami_ai_patente_bot.models import (
    QuizExplanation,
    QuizQuestion,
    QuizSession,
    SessionSummary,
)


@service
class QuizFlowService:
    """Orchestrates one chat's question/answer loop over `QuizApiClient` (AD-5, AD-6).

    The only place in the bot with orchestration logic: handlers call exactly one of
    its methods and never depend on `QuizApiClient` directly.
    """

    api: Autowired[QuizApiClient]

    async def propose_question(
        self, session: QuizSession | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        """Proposes the next question in the chat's seeded permutation (FR-1, FR-4).

        A `None` session starts a fresh permutation with a freshly generated seed at
        `index=0`; an existing session reuses its seed and advances `index` by one.
        """
        seed = session.seed if session is not None else uuid.uuid4().hex
        index = session.index + 1 if session is not None else 0
        question = await self.api.propose_question(telegram_user_id, seed, index)
        new_session = QuizSession(seed=seed, index=index, current_question_number=question.number)
        return question, new_session

    async def handle_answer(
        self, session: QuizSession | None, number: str, answer: bool, telegram_user_id: int
    ) -> tuple[bool, ExplanationStatus]:
        """Grades `answer` and advertises the explanation status (FR-2; spec 0017 FR-1).

        The session's own seed is sent as the backend's `session_id` (spec 0016,
        D-12) — the bot never invents a second identifier for the same concept. The
        explanation is deliberately not fetched here anymore (spec 0017): the caller
        renders a "Spiega" button instead and calls `handle_explanation_request` only
        if the user taps it.

        Raises:
            StaleQuestionError: `number` is not the chat's current question (FR-3).
        """
        if session is None or session.current_question_number != number:
            raise StaleQuestionError(number)
        return await self.api.check_answer(telegram_user_id, number, answer, session.seed)

    async def handle_explanation_request(
        self, number: str, telegram_user_id: int, submitted: bool
    ) -> QuizExplanation:
        """Ensures the labeling, then fetches the explanation, in sequence (spec 0017 FR-3).

        `label_question` is always called first and awaited, unconditionally (AD-5):
        even when the check-time status was already cached, the extra call is a
        cheap cache read. Either call failing falls back to the same "no
        explanation available" rendering (AD-12) — `label_question`'s own failure
        short-circuits before `get_explanation` is ever called.
        """
        try:
            await self.api.label_question(telegram_user_id, number)
            return await self.api.get_explanation(telegram_user_id, number, submitted=submitted)
        except QuizApiError:
            return QuizExplanation(
                status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE, explanation=None
            )

    async def handle_translation_request(self, text: str, telegram_user_id: int) -> str:
        """Translates `text` to Russian (spec 0018 bot UX).

        Takes the already-validated explanation text directly rather than a
        session/number pair, mirroring `handle_explanation_request`'s own shape:
        the caller (the "Traduci" tap handler) is responsible for staleness
        checking before this runs — by the time it is called, `text` is already
        known to be the chat's current, previously-shown explanation.

        Raises:
            QuizApiError: The translation call failed. Left to propagate, unlike
                `handle_explanation_request`'s fallback: the caller needs to
                distinguish success from failure to decide between showing the
                translation and reverting its optimistic edit with a retry
                affordance (spec 0018 bot UX).
        """
        return await self.api.translate_explanation(telegram_user_id, text)

    async def download_image(self, image_url: str, telegram_user_id: int) -> bytes:
        """Passes through to `QuizApiClient` so handlers never depend on it directly (AD-5)."""
        return await self.api.download_image(telegram_user_id, image_url)

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        """Passes through to `GET /me` (spec 0016, FR-2)."""
        return await self.api.check_registration_status(telegram_user_id)

    async def session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        """Passes through to `GET /quiz-answers/summary` (spec 0016, FR-9)."""
        return await self.api.get_session_summary(telegram_user_id, session_id)
