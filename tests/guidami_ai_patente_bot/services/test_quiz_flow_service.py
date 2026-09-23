"""QuizFlowService derives session state and enforces the FR-3 stale-button guard."""

from dataclasses import dataclass, field

import pytest

from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus
from guidami_ai_patente_bot.exceptions import QuizApiError, StaleQuestionError
from guidami_ai_patente_bot.models import (
    CitedGlossaryTerm,
    QuizExplanation,
    QuizQuestion,
    QuizSession,
    SessionSummary,
)
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
    explanation_status: ExplanationStatus = ExplanationStatus.CACHED
    raise_label_error: bool = False
    raise_explanation_error: bool = False
    translation: str = "Перевод."
    raise_translate_error: bool = False
    translate_calls: list[tuple[int, str, tuple[CitedGlossaryTerm, ...]]] = field(
        default_factory=list
    )
    registered: bool = True
    summary: SessionSummary = field(
        default_factory=lambda: SessionSummary(
            answered=0, correct=0, by_topic=[], wrong_questions=[]
        )
    )
    propose_calls: list[tuple[int, str, int]] = field(default_factory=list)
    check_calls: list[tuple[int, str, bool, str]] = field(default_factory=list)
    label_calls: list[tuple[int, str]] = field(default_factory=list)
    explanation_calls: list[tuple[int, str, bool]] = field(default_factory=list)
    registration_calls: list[int] = field(default_factory=list)
    summary_calls: list[tuple[int, str]] = field(default_factory=list)

    async def propose_question(self, telegram_user_id: int, seed: str, index: int) -> QuizQuestion:
        self.propose_calls.append((telegram_user_id, seed, index))
        return self.question

    async def check_answer(
        self, telegram_user_id: int, number: str, answer: bool, session_id: str
    ) -> tuple[bool, ExplanationStatus]:
        self.check_calls.append((telegram_user_id, number, answer, session_id))
        return self.correct, self.explanation_status

    async def label_question(self, telegram_user_id: int, number: str) -> None:
        self.label_calls.append((telegram_user_id, number))
        if self.raise_label_error:
            raise QuizApiError("boom")

    async def get_explanation(
        self, telegram_user_id: int, number: str, submitted: bool
    ) -> QuizExplanation:
        self.explanation_calls.append((telegram_user_id, number, submitted))
        if self.raise_explanation_error:
            raise QuizApiError("boom")
        return self.explanation

    async def translate_explanation(
        self, telegram_user_id: int, text: str, hints: tuple[CitedGlossaryTerm, ...] = ()
    ) -> str:
        self.translate_calls.append((telegram_user_id, text, hints))
        if self.raise_translate_error:
            raise QuizApiError("boom")
        return self.translation

    async def download_image(self, telegram_user_id: int, image_url: str) -> bytes:
        return b"image"

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        self.registration_calls.append(telegram_user_id)
        return self.registered

    async def get_session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        self.summary_calls.append((telegram_user_id, session_id))
        return self.summary


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

    _, session = await service.propose_question(None, 7)

    assert api.propose_calls == [(7, session.seed, 0)]
    assert session.index == 0


@pytest.mark.asyncio
async def test_an_existing_session_reuses_the_seed_and_advances_the_index() -> None:
    api = _ApiDouble(question=_question("0002"))
    service = _service(api)
    previous = QuizSession(seed="abc", index=3, current_question_number="0001")

    _, session = await service.propose_question(previous, 7)

    assert api.propose_calls == [(7, "abc", 4)]
    assert session.seed == "abc"
    assert session.index == 4
    assert session.current_question_number == "0002"


@pytest.mark.asyncio
async def test_a_matching_answer_is_graded_and_the_status_is_returned() -> None:
    """Spec 0017 FR-1: the explanation is no longer fetched here."""
    api = _ApiDouble(
        question=_question(), correct=True, explanation_status=ExplanationStatus.CACHED
    )
    service = _service(api)
    session = QuizSession(seed="abc", index=0, current_question_number="0001")

    correct, status = await service.handle_answer(session, "0001", True, 7)

    assert correct is True
    assert status is ExplanationStatus.CACHED
    assert api.check_calls == [(7, "0001", True, "abc")]
    assert api.explanation_calls == [], "spec 0017: handle_answer never fetches the explanation"


@pytest.mark.asyncio
async def test_a_stale_number_raises_without_calling_the_api() -> None:
    api = _ApiDouble(question=_question())
    service = _service(api)
    session = QuizSession(seed="abc", index=0, current_question_number="0001")

    with pytest.raises(StaleQuestionError):
        await service.handle_answer(session, "0002", True, 7)

    assert api.check_calls == []


@pytest.mark.asyncio
async def test_no_session_at_all_is_also_stale() -> None:
    api = _ApiDouble(question=_question())
    service = _service(api)

    with pytest.raises(StaleQuestionError):
        await service.handle_answer(None, "0001", True, 7)


@pytest.mark.asyncio
async def test_an_explanation_request_labels_then_explains_in_sequence() -> None:
    """Spec 0017 FR-3, AD-5: /label is always called first, unconditionally."""
    api = _ApiDouble(question=_question())
    service = _service(api)

    explanation = await service.handle_explanation_request("0001", 7, True)

    assert explanation.status is ExplanationOutcome.EXPLAINED
    assert api.label_calls == [(7, "0001")]
    assert api.explanation_calls == [(7, "0001", True)]


@pytest.mark.asyncio
async def test_a_failed_label_call_falls_back_to_no_explanation_available() -> None:
    api = _ApiDouble(question=_question(), raise_label_error=True)
    service = _service(api)

    explanation = await service.handle_explanation_request("0001", 7, True)

    assert explanation.status is ExplanationOutcome.INSUFFICIENT_KNOWLEDGE
    assert explanation.explanation is None
    assert api.explanation_calls == [], "a failed /label must not be followed by /explanation"


@pytest.mark.asyncio
async def test_a_failed_explanation_call_falls_back_to_no_explanation_available() -> None:
    api = _ApiDouble(question=_question(), raise_explanation_error=True)
    service = _service(api)

    explanation = await service.handle_explanation_request("0001", 7, True)

    assert explanation.status is ExplanationOutcome.INSUFFICIENT_KNOWLEDGE
    assert explanation.explanation is None
    assert api.label_calls == [(7, "0001")]


@pytest.mark.asyncio
async def test_check_registration_status_passes_through() -> None:
    api = _ApiDouble(question=_question(), registered=True)
    service = _service(api)

    registered = await service.check_registration_status(7)

    assert registered is True
    assert api.registration_calls == [7]


@pytest.mark.asyncio
async def test_session_summary_passes_through() -> None:
    expected = SessionSummary(answered=5, correct=3, by_topic=[], wrong_questions=[])
    api = _ApiDouble(question=_question(), summary=expected)
    service = _service(api)

    summary = await service.session_summary(7, "seed-abc")

    assert summary == expected
    assert api.summary_calls == [(7, "seed-abc")]


@pytest.mark.asyncio
async def test_a_translation_request_delegates_to_the_api() -> None:
    """Spec 0018 bot UX: the caller already validated staleness; this just calls through."""
    api = _ApiDouble(question=_question(), translation="Перевод.")
    service = _service(api)

    translated = await service.handle_translation_request("Testo da tradurre.", 7, ())

    assert translated == "Перевод."
    assert api.translate_calls == [(7, "Testo da tradurre.", ())]


@pytest.mark.asyncio
async def test_a_translation_request_forwards_hints() -> None:
    """Spec 0020 FR-7: the glossary hints shown alongside the explanation are forwarded."""
    hints = (CitedGlossaryTerm(term="banchina", definition="...", term_ru="обочина"),)
    api = _ApiDouble(question=_question(), translation="Перевод.")
    service = _service(api)

    await service.handle_translation_request("Testo da tradurre.", 7, hints)

    assert api.translate_calls == [(7, "Testo da tradurre.", hints)]


@pytest.mark.asyncio
async def test_a_translation_api_failure_propagates() -> None:
    api = _ApiDouble(question=_question(), raise_translate_error=True)
    service = _service(api)

    with pytest.raises(QuizApiError):
        await service.handle_translation_request("Testo da tradurre.", 7, ())
