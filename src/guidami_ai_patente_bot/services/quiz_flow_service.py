"""Sequences propose/answer calls against the API and derives the chat's session state."""

import uuid

from pywire import Autowired, service

from guidami_ai_patente_bot.clients import QuizApiClient
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus, SessionMode
from guidami_ai_patente_bot.exceptions import (
    QuizApiError,
    SessionCompletedError,
    StaleQuestionError,
)
from guidami_ai_patente_bot.models import (
    CitedGlossaryTerm,
    QuizExplanation,
    QuizQuestion,
    QuizSession,
    SessionSummary,
    UserStatistics,
)


@service
class QuizFlowService:
    """Orchestrates one chat's question/answer loop over `QuizApiClient` (AD-5, AD-6, AD-7).

    Dispatches question proposals on the session's mode (random, topic, review).

    The only place in the bot with orchestration logic: handlers call exactly one of
    its methods and never depend on `QuizApiClient` directly.
    """

    api: Autowired[QuizApiClient]

    async def start_session(
        self, mode: SessionMode, topic: str | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        """Starts a fresh session in `mode` at `index=0` with a newly generated seed (AD-7).

        The seed doubles as the backend's `session_id` in every mode.

        Raises:
            SessionCompletedError: The mode has nothing to propose (empty topic, or
                nothing left to review).
        """
        return await self._propose(mode, topic, uuid.uuid4().hex, 0, telegram_user_id)

    async def propose_question(
        self, session: QuizSession | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        """Proposes the next question for the session's mode (FR-1, FR-4, FR-7, FR-8).

        A `None` session starts a fresh RANDOM permutation; an existing session keeps
        its seed, mode and topic and advances `index` by one. RANDOM draws from the
        seeded permutation, TOPIC from the same permutation restricted to the topic,
        REVIEW from the review queue keyed by the seed as `session_id`.

        Raises:
            SessionCompletedError: A TOPIC or REVIEW session has no more questions.
                Never raised in RANDOM, where a backend 404 stays a `QuizApiError`.
        """
        if session is None:
            return await self.start_session(SessionMode.RANDOM, None, telegram_user_id)
        return await self._propose(
            session.mode, session.topic, session.seed, session.index + 1, telegram_user_id
        )

    async def _propose(
        self, mode: SessionMode, topic: str | None, seed: str, index: int, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        """Fetches the question at `index` for `mode` and builds the resulting session."""
        match mode:
            case SessionMode.REVIEW:
                question = await self.api.propose_review_question(telegram_user_id, seed)
            case SessionMode.TOPIC:
                question = await self.api.propose_question(telegram_user_id, seed, index, topic)
            case SessionMode.RANDOM:
                question = await self.api.propose_question(telegram_user_id, seed, index)
        if question is None:
            if mode is SessionMode.RANDOM:
                raise QuizApiError("random proposal returned no question without a topic filter")
            raise SessionCompletedError(mode)
        new_session = QuizSession(
            seed=seed,
            index=index,
            current_question_number=question.number,
            mode=mode,
            topic=topic,
        )
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

    async def handle_translation_request(
        self, text: str, telegram_user_id: int, hints: tuple[CitedGlossaryTerm, ...]
    ) -> str:
        """Translates `text` to Russian, forwarding `hints` (spec 0018 bot UX, spec 0020 FR-7).

        Takes the already-validated explanation text directly rather than a
        session/number pair, mirroring `handle_explanation_request`'s own shape:
        the caller (the "Traduci" tap handler) is responsible for staleness
        checking before this runs — by the time it is called, `text` is already
        known to be the chat's current, previously-shown explanation. `hints` is
        `session.last_explanation_hints`, passed through unchanged to
        `QuizApiClient.translate_explanation`.

        Raises:
            QuizApiError: The translation call failed. Left to propagate, unlike
                `handle_explanation_request`'s fallback: the caller needs to
                distinguish success from failure to decide between showing the
                translation and reverting its optimistic edit with a retry
                affordance (spec 0018 bot UX).
        """
        return await self.api.translate_explanation(telegram_user_id, text, hints)

    async def download_image(self, image_url: str, telegram_user_id: int) -> bytes:
        """Passes through to `QuizApiClient` so handlers never depend on it directly (AD-5)."""
        return await self.api.download_image(telegram_user_id, image_url)

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        """Passes through to `GET /me` (spec 0016, FR-2)."""
        return await self.api.check_registration_status(telegram_user_id)

    async def session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        """Passes through to `GET /quiz-answers/summary` (spec 0016, FR-9)."""
        return await self.api.get_session_summary(telegram_user_id, session_id)

    async def get_statistics(self, telegram_user_id: int) -> UserStatistics:
        """Passes through to `GET /quiz-answers/statistics` so handlers never use the client."""
        return await self.api.get_statistics(telegram_user_id)
