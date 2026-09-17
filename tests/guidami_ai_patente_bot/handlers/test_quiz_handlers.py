"""Telegram handlers are thin controllers over QuizFlowService (AD-5, spec 0016)."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guidami_ai_patente_bot import container
from guidami_ai_patente_bot.enums import ExplanationOutcome
from guidami_ai_patente_bot.exceptions import StaleQuestionError
from guidami_ai_patente_bot.handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    handle_answer_callback,
    handle_next_callback,
    quiz_command,
    start_command,
)
from guidami_ai_patente_bot.models import QuizExplanation, QuizQuestion, QuizSession
from guidami_ai_patente_bot.services import QuizFlowService

_TELEGRAM_USER_ID = 7


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
    registered: bool = True
    propose_calls: list[int] = field(default_factory=list)
    handle_answer_calls: list[tuple[str, bool, int]] = field(default_factory=list)
    registration_calls: list[int] = field(default_factory=list)

    async def propose_question(
        self, session: QuizSession | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        self.propose_calls.append(telegram_user_id)
        index = session.index + 1 if session is not None else 0
        seed = session.seed if session is not None else "seed"
        new_session = QuizSession(
            seed=seed, index=index, current_question_number=self.question.number
        )
        return self.question, new_session

    async def handle_answer(
        self, session: QuizSession | None, number: str, answer: bool, telegram_user_id: int
    ) -> tuple[bool, QuizExplanation]:
        self.handle_answer_calls.append((number, answer, telegram_user_id))
        if self.raise_stale:
            raise StaleQuestionError(number)
        return self.correct, self.explanation

    async def download_image(self, image_url: str, telegram_user_id: int) -> bytes:
        return b"image-bytes"

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        self.registration_calls.append(telegram_user_id)
        return self.registered


class _StubContainer:
    """Minimal resolve()-only stand-in for pywire's container, bound via `bot_data`."""

    def __init__(self, service: _FlowServiceDouble) -> None:
        self._service = service

    def resolve(self, target_type: type) -> object:
        assert target_type is QuizFlowService
        return self._service


def _context(double: _FlowServiceDouble) -> SimpleNamespace:
    return SimpleNamespace(
        bot=AsyncMock(),
        user_data={},
        bot_data={container.BOT_DATA_CONTAINER_KEY: _StubContainer(double)},
    )


def _update(chat_id: int = 123, user_id: int = _TELEGRAM_USER_ID) -> SimpleNamespace:
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id), effective_user=SimpleNamespace(id=user_id)
    )


def _callback_update(
    data: str, *, has_photo: bool = False, user_id: int = _TELEGRAM_USER_ID
) -> tuple[SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(photo=(b"x",) if has_photo else ())
    query = SimpleNamespace(
        data=data,
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_caption=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=user_id),
        callback_query=query,
    )
    return update, query


def _question() -> QuizQuestion:
    return QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)


@pytest.mark.asyncio
async def test_start_shows_the_welcome_message_when_registered() -> None:
    double = _FlowServiceDouble(question=_question(), registered=True)
    context = _context(double)

    await start_command(_update(), context)

    assert double.registration_calls == [_TELEGRAM_USER_ID]
    assert double.propose_calls == [], "FR-7: /start never proposes a question"
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_shows_the_pending_approval_message_when_unregistered() -> None:
    context = _context(_FlowServiceDouble(question=_question(), registered=False))

    await start_command(_update(), context)

    text = context.bot.send_message.call_args.kwargs["text"]
    assert "attesa" in text.lower()


@pytest.mark.asyncio
async def test_quiz_sends_a_text_message_when_the_question_has_no_image() -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    double = _FlowServiceDouble(question=question)
    context = _context(double)

    await quiz_command(_update(), context)

    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == "Domanda?"
    assert context.user_data["session"].current_question_number == "0001"
    assert double.propose_calls == [_TELEGRAM_USER_ID]


@pytest.mark.asyncio
async def test_quiz_sends_a_photo_when_the_question_has_an_image() -> None:
    question = QuizQuestion(
        number="0001", topic="segnaletica", text="Domanda?", image_url="/quiz-images/x.jpg"
    )
    context = _context(_FlowServiceDouble(question=question))

    await quiz_command(_update(), context)

    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.call_args.kwargs["caption"] == "Domanda?"


@pytest.mark.asyncio
async def test_next_callback_acks_then_proposes_a_question() -> None:
    question = QuizQuestion(number="0002", topic="segnaletica", text="Altra?", image_url=None)
    context = _context(_FlowServiceDouble(question=question))
    update, query = _callback_update("quiz:next")

    await handle_next_callback(update, context)

    query.answer.assert_awaited_once_with()
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_valid_answer_edits_the_text_message_with_the_outcome() -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    double = _FlowServiceDouble(question=question, correct=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    query.edit_message_text.assert_awaited_once()
    assert "corretta" in query.edit_message_text.call_args.kwargs["text"]
    assert double.handle_answer_calls == [("0001", True, _TELEGRAM_USER_ID)]


@pytest.mark.asyncio
async def test_a_valid_answer_on_a_photo_message_edits_the_caption() -> None:
    question = QuizQuestion(
        number="0001", topic="segnaletica", text="Domanda?", image_url="/x.jpg"
    )
    context = _context(_FlowServiceDouble(question=question, correct=False))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:0", has_photo=True)

    await handle_answer_callback(update, context)

    query.edit_message_caption.assert_awaited_once()
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_insufficient_knowledge_shows_the_fallback_line() -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    explanation = QuizExplanation(
        status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE, explanation=None
    )
    context = _context(
        _FlowServiceDouble(question=question, explanation=explanation, correct=True)
    )
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    assert "Nessuna spiegazione" in query.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_a_stale_answer_gets_a_notice_and_no_edit() -> None:
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    context = _context(_FlowServiceDouble(question=question, raise_stale=True))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0002:1")

    await handle_answer_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    query.edit_message_text.assert_not_awaited()
    query.edit_message_caption.assert_not_awaited()
