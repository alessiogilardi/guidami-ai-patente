"""SessionSummaryService delegates straight to the repository (spec 0016, FR-9)."""

from dataclasses import dataclass

import pytest

from guidami_ai_patente.models import (
    SessionSummary,
    SessionSummaryRequest,
    TopicSummary,
    WrongQuestion,
)
from guidami_ai_patente.services import SessionSummaryService


@dataclass
class _AnswersDouble:
    summary: SessionSummary
    calls: list[tuple[int, str]]

    def session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        self.calls.append((telegram_user_id, session_id))
        return self.summary


@pytest.mark.asyncio
async def test_it_passes_the_callers_identity_and_session_through() -> None:
    summary = SessionSummary(
        answered=5,
        correct=3,
        by_topic=[TopicSummary(topic="segnaletica", answered=5, correct=3)],
        wrong_questions=[WrongQuestion(number="0001", text="Domanda?")],
    )
    answers = _AnswersDouble(summary=summary, calls=[])
    service = object.__new__(SessionSummaryService)
    service.answers = answers  # type: ignore[assignment]

    result = await service(SessionSummaryRequest(telegram_user_id=42, session_id="seed-abc"))

    assert result == summary
    assert answers.calls == [(42, "seed-abc")]
