"""Telegram handlers are thin controllers over QuizFlowService (AD-5)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guidami_ai_patente_bot.enums import ExplanationOutcome
from guidami_ai_patente_bot.exceptions import StaleQuestionError
from guidami_ai_patente_bot.handlers import quiz_handlers
from guidami_ai_patente_bot.handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    handle_answer_callback,
    handle_next_callback,
    start_or_quiz,
)
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion, QuizSession
from guidami_ai_patente_bot.services import QuizFlowService


@dataclass
class _FlowServiceDouble:
    question: QuizQuestion
    explanation: QuizExplanation = field(
        default_factory=lambda: QuizExplanation(
            status=ExplanationOutcome.EXPLAINED, explanation="perché..."
        )
    )
    correct: bool = True
    raise_stale: bool = False
    handle_answer_calls: list[tuple[str, bool]] = field(default_factory=list)

    async def propose_question(
        self, session: QuizSession | None
    ) -> tuple[QuizQuestion, QuizSession]:
        index = session.index + 1 if session is not None else 0
        seed = session.seed if session is not None else "seed"
        new_session = QuizSession(
            seed=seed, index=index, current_question_number=self.question.number
        )
        return self.question, new_session

    async def handle_answer(
        self, session: QuizSession | None, number: str, answer: bool
    ) -> tuple[bool, QuizExplanation]:
        self.handle_answer_calls.append((number, answer))
        if self.raise_stale:
            raise StaleQuestionError(number)
        return self.correct, self.explanation

    async def download_image(self, image_url: str) -> bytes:
        return b"image-bytes"


class _StubContainer:
    """Minimal resolve()-only stand-in for pywire's container.

    pywire's real `Container._put` refuses to let `register_instance` override
    a key `@service` already auto-registered at import time, so the fixture
    below intercepts `quiz_handlers.get_default_container` instead of touching
    the real container's registry.
    """

    def __init__(self, service: _FlowServiceDouble) -> None:
        self._service = service

    def resolve(self, target_type: type) -> object:
        assert target_type is QuizFlowService
        return self._service


@pytest.fixture
def register_flow_service(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[_FlowServiceDouble], _FlowServiceDouble]:
    def _register(double: _FlowServiceDouble) -> _FlowServiceDouble:
        monkeypatch.setattr(quiz_handlers, "get_default_container", lambda: _StubContainer(double))
        return double

    return _register


def _context() -> SimpleNamespace:
    return SimpleNamespace(bot=AsyncMock(), user_data={})


def _update(chat_id: int = 123) -> SimpleNamespace:
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id))


def _callback_update(
    data: str, *, has_photo: bool = False
) -> tuple[SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(photo=(b"x",) if has_photo else ())
    query = SimpleNamespace(
        data=data,
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_caption=AsyncMock(),
    )
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), callback_query=query)
    return update, query


@pytest.mark.asyncio
async def test_start_sends_a_text_message_when_the_question_has_no_image(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    register_flow_service(_FlowServiceDouble(question=question))
    context = _context()

    await start_or_quiz(_update(), context)

    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == "Domanda?"
    assert context.user_data["session"].current_question_number == "0001"


@pytest.mark.asyncio
async def test_start_sends_a_photo_when_the_question_has_an_image(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(
        number="0001", topic="segnaletica", text="Domanda?", image_url="/quiz-images/x.jpg"
    )
    register_flow_service(_FlowServiceDouble(question=question))
    context = _context()

    await start_or_quiz(_update(), context)

    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.call_args.kwargs["caption"] == "Domanda?"


@pytest.mark.asyncio
async def test_next_callback_acks_then_proposes_a_question(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(number="0002", topic="segnaletica", text="Altra?", image_url=None)
    register_flow_service(_FlowServiceDouble(question=question))
    context = _context()
    update, query = _callback_update("quiz:next")

    await handle_next_callback(update, context)

    query.answer.assert_awaited_once_with()
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_valid_answer_edits_the_text_message_with_the_outcome(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    register_flow_service(_FlowServiceDouble(question=question, correct=True))
    context = _context()
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    query.edit_message_text.assert_awaited_once()
    assert "corretta" in query.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_a_valid_answer_on_a_photo_message_edits_the_caption(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(
        number="0001", topic="segnaletica", text="Domanda?", image_url="/x.jpg"
    )
    register_flow_service(_FlowServiceDouble(question=question, correct=False))
    context = _context()
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:0", has_photo=True)

    await handle_answer_callback(update, context)

    query.edit_message_caption.assert_awaited_once()
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_insufficient_knowledge_shows_the_fallback_line(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    explanation = QuizExplanation(
        status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE, explanation=None
    )
    register_flow_service(
        _FlowServiceDouble(question=question, explanation=explanation, correct=True)
    )
    context = _context()
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    assert "Nessuna spiegazione" in query.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_a_stale_answer_gets_a_notice_and_no_edit(
    register_flow_service: Callable[[_FlowServiceDouble], _FlowServiceDouble],
) -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    register_flow_service(_FlowServiceDouble(question=question, raise_stale=True))
    context = _context()
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0002:1")

    await handle_answer_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    query.edit_message_text.assert_not_awaited()
    query.edit_message_caption.assert_not_awaited()
