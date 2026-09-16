"""Sequences propose/answer calls against the API and derives the chat's session state."""

import uuid

from pywire import Autowired, service

from guidami_ai_patente_bot.clients import QuizApiClient
from guidami_ai_patente_bot.exceptions import StaleQuestionError
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion, QuizSession


@service
class QuizFlowService:
    """Orchestrates one chat's question/answer loop over `QuizApiClient` (AD-5, AD-6).

    The only place in the bot with orchestration logic: handlers call exactly one of
    its three methods and never depend on `QuizApiClient` directly.
    """

    api: Autowired[QuizApiClient]

    async def propose_question(
        self, session: QuizSession | None
    ) -> tuple[QuizQuestion, QuizSession]:
        """Proposes the next question in the chat's seeded permutation (FR-1, FR-4).

        A `None` session starts a fresh permutation with a freshly generated seed at
        `index=0`; an existing session reuses its seed and advances `index` by one —
        the same rule for a repeated `/quiz` and for "Prossima domanda" (FR-1 AC, FR-4).
        """
        seed = session.seed if session is not None else uuid.uuid4().hex
        index = session.index + 1 if session is not None else 0
        question = await self.api.propose_question(seed, index)
        new_session = QuizSession(seed=seed, index=index, current_question_number=question.number)
        return question, new_session

    async def handle_answer(
        self, session: QuizSession | None, number: str, answer: bool
    ) -> tuple[bool, QuizExplanation]:
        """Grades `answer` and fetches its explanation in the same turn (FR-2).

        Raises:
            StaleQuestionError: `number` is not the chat's current question — no
                session at all, or a session pointing at a different one (FR-3).
        """
        if session is None or session.current_question_number != number:
            raise StaleQuestionError(number)
        correct = await self.api.check_answer(number, answer)
        explanation = await self.api.get_explanation(number, submitted=answer)
        return correct, explanation

    async def download_image(self, image_url: str) -> bytes:
        """Passes through to `QuizApiClient` so handlers never depend on it directly (AD-5)."""
        return await self.api.download_image(image_url)
