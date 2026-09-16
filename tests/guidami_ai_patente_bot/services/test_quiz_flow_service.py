"""QuizFlowService derives session state and enforces the FR-3 stale-button guard."""

from dataclasses import dataclass, field

import pytest

from guidami_ai_patente_bot.enums import ExplanationOutcome
from guidami_ai_patente_bot.exceptions import StaleQuestionError
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion, QuizSession
from guidami_ai_patente_bot.services import QuizFlowService


@dataclass
class _ApiDouble:
    question: QuizQuestion
    explanation: QuizExplanation = field(
        default_factory=lambda: QuizExplanation(
            status=ExplanationOutcome.EXPLAINED, explanation="..."
        )
    )
    correct: bool = True
    propose_calls: list[tuple[str, int]] = field(default_factory=list)
    check_calls: list[tuple[str, bool]] = field(default_factory=list)

    async def propose_question(self, seed: str, index: int) -> QuizQuestion:
        self.propose_calls.append((seed, index))
        return self.question

    async def check_answer(self, number: str, answer: bool) -> bool:
        self.check_calls.append((number, answer))
        return self.correct

    async def get_explanation(self, number: str, submitted: bool) -> QuizExplanation:
        return self.explanation

    async def download_image(self, image_url: str) -> bytes:
        return b"image"


def _question(number: str = "0001") -> QuizQuestion:
    return QuizQuestion(number=number, topic="segnaletica", text="...", image_url=None)


def _service(api: _ApiDouble) -> QuizFlowService:
    """Sidesteps pywire's container, same pattern as `test_quiz_answer_checker.py`."""
    service = object.__new__(QuizFlowService)
    service.api = api  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_a_fresh_session_proposes_index_zero_with_a_new_seed() -> None:
    api = _ApiDouble(question=_question())
    service = _service(api)

    _, session = await service.propose_question(None)

    assert api.propose_calls == [(session.seed, 0)]
    assert session.index == 0


@pytest.mark.asyncio
async def test_an_existing_session_reuses_the_seed_and_advances_the_index() -> None:
    api = _ApiDouble(question=_question("0002"))
    service = _service(api)
    previous = QuizSession(seed="abc", index=3, current_question_number="0001")

    _, session = await service.propose_question(previous)

    assert api.propose_calls == [("abc", 4)]
    assert session.seed == "abc"
    assert session.index == 4
    assert session.current_question_number == "0002"


@pytest.mark.asyncio
async def test_a_matching_answer_is_checked_and_explained() -> None:
    api = _ApiDouble(question=_question(), correct=True)
    service = _service(api)
    session = QuizSession(seed="abc", index=0, current_question_number="0001")

    correct, explanation = await service.handle_answer(session, "0001", True)

    assert correct is True
    assert explanation.status is ExplanationOutcome.EXPLAINED
    assert api.check_calls == [("0001", True)]


@pytest.mark.asyncio
async def test_a_stale_number_raises_without_calling_the_api() -> None:
    api = _ApiDouble(question=_question())
    service = _service(api)
    session = QuizSession(seed="abc", index=0, current_question_number="0001")

    with pytest.raises(StaleQuestionError):
        await service.handle_answer(session, "0002", True)

    assert api.check_calls == []


@pytest.mark.asyncio
async def test_no_session_at_all_is_also_stale() -> None:
    api = _ApiDouble(question=_question())
    service = _service(api)

    with pytest.raises(StaleQuestionError):
        await service.handle_answer(None, "0001", True)
