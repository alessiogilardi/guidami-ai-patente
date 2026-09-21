"""Telegram handlers are thin controllers over QuizFlowService (AD-5, spec 0016/0017/0018)."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guidami_ai_patente_bot import container, messages
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus
from guidami_ai_patente_bot.exceptions import QuizApiError, StaleQuestionError
from guidami_ai_patente_bot.handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    EXPLAIN_CALLBACK_PREFIX,
    TRANSLATE_CALLBACK_PREFIX,
    handle_answer_callback,
    handle_explain_callback,
    handle_next_callback,
    handle_translate_callback,
    quiz_command,
    start_command,
    stop_command,
)
from guidami_ai_patente_bot.models import (
    QuizExplanation,
    QuizQuestion,
    QuizSession,
    SessionSummary,
)
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
    explanation_status: ExplanationStatus = ExplanationStatus.CACHED
    translation: str = "Перевод."
    raise_stale: bool = False
    raise_translate_error: bool = False
    registered: bool = True
    propose_calls: list[int] = field(default_factory=list)
    handle_answer_calls: list[tuple[str, bool, int]] = field(default_factory=list)
    explanation_request_calls: list[tuple[str, int, bool]] = field(default_factory=list)
    translate_request_calls: list[tuple[str, int]] = field(default_factory=list)
    registration_calls: list[int] = field(default_factory=list)
    summary: SessionSummary = field(default_factory=lambda: SessionSummary(answered=0, correct=0))
    raise_summary_error: bool = False
    summary_calls: list[tuple[int, str]] = field(default_factory=list)

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
    ) -> tuple[bool, ExplanationStatus]:
        self.handle_answer_calls.append((number, answer, telegram_user_id))
        if self.raise_stale:
            raise StaleQuestionError(number)
        return self.correct, self.explanation_status

    async def handle_explanation_request(
        self, number: str, telegram_user_id: int, submitted: bool
    ) -> QuizExplanation:
        self.explanation_request_calls.append((number, telegram_user_id, submitted))
        return self.explanation

    async def handle_translation_request(self, text: str, telegram_user_id: int) -> str:
        self.translate_request_calls.append((text, telegram_user_id))
        if self.raise_translate_error:
            raise QuizApiError("boom")
        return self.translation

    async def download_image(self, image_url: str, telegram_user_id: int) -> bytes:
        return b"image-bytes"

    async def check_registration_status(self, telegram_user_id: int) -> bool:
        self.registration_calls.append(telegram_user_id)
        return self.registered

    async def session_summary(self, telegram_user_id: int, session_id: str) -> SessionSummary:
        self.summary_calls.append((telegram_user_id, session_id))
        if self.raise_summary_error:
            raise QuizApiError("boom")
        return self.summary


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
    data: str,
    *,
    has_photo: bool = False,
    user_id: int = _TELEGRAM_USER_ID,
    text: str = "❌ Risposta sbagliata.",
) -> tuple[SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(
        photo=(b"x",) if has_photo else (),
        text=None if has_photo else text,
        caption=text if has_photo else None,
    )
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


def _button_texts(keyboard: object) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_start_shows_the_welcome_message_when_registered() -> None:
    double = _FlowServiceDouble(question=_question(), registered=True)
    context = _context(double)

    await start_command(_update(), context)

    assert double.registration_calls == [_TELEGRAM_USER_ID]
    assert double.propose_calls == [], "FR-7: /start never proposes a question"
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_lists_the_available_commands_when_registered() -> None:
    context = _context(_FlowServiceDouble(question=_question(), registered=True))

    await start_command(_update(), context)

    text = context.bot.send_message.call_args.kwargs["text"]
    assert "/quiz" in text
    assert "/stop" in text


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

    assert context.bot.send_message.call_args.kwargs["text"] == "Domanda?"
    assert context.user_data["session"].current_question_number == "0001"
    assert double.propose_calls == [_TELEGRAM_USER_ID]


@pytest.mark.asyncio
async def test_quiz_introduces_the_session_before_the_first_question() -> None:
    """A new session (no `session` in user_data yet) opens with the intro, then the question."""
    context = _context(_FlowServiceDouble(question=_question()))

    await quiz_command(_update(), context)

    sent_texts = [call.kwargs["text"] for call in context.bot.send_message.await_args_list]
    assert sent_texts == [messages.QUIZ_INTRO_MESSAGE, "Domanda?"]
    assert "/stop" in messages.QUIZ_INTRO_MESSAGE


@pytest.mark.asyncio
async def test_quiz_resuming_a_pending_session_skips_the_intro() -> None:
    context = _context(_FlowServiceDouble(question=_question()))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")

    await quiz_command(_update(), context)

    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == "Domanda?"


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
async def test_a_valid_answer_edits_the_text_message_with_the_outcome_and_offers_to_explain() -> (
    None
):
    """Spec 0017 FR-1: the explanation is not shown yet, only the outcome and the buttons."""
    question = QuizQuestion(number="0001", topic="segnaletica", text="Domanda?", image_url=None)
    double = _FlowServiceDouble(
        question=question, correct=True, explanation_status=ExplanationStatus.CACHED
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    query.edit_message_text.assert_awaited_once()
    call = query.edit_message_text.call_args
    assert "corretta" in call.kwargs["text"]
    assert double.handle_answer_calls == [("0001", True, _TELEGRAM_USER_ID)]
    assert double.explanation_request_calls == [], "spec 0017: no explanation fetched on grading"
    assert _button_texts(call.kwargs["reply_markup"]) == ["Spiega", "Prossima domanda ▶"]


@pytest.mark.asyncio
async def test_a_valid_answer_keeps_the_question_text_above_the_outcome() -> None:
    """The user must not lose the question they just answered."""
    context = _context(_FlowServiceDouble(question=_question(), correct=False))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1", text="Domanda?")

    await handle_answer_callback(update, context)

    text = query.edit_message_text.call_args.kwargs["text"]
    assert text == f"Domanda?\n\n{messages.outcome_line(False)}"


@pytest.mark.asyncio
async def test_a_valid_answer_on_a_photo_message_keeps_the_question_in_the_caption() -> None:
    context = _context(_FlowServiceDouble(question=_question(), correct=True))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(
        f"{ANSWER_CALLBACK_PREFIX}0001:1", has_photo=True, text="Domanda?"
    )

    await handle_answer_callback(update, context)

    caption = query.edit_message_caption.call_args.kwargs["caption"]
    assert caption == f"Domanda?\n\n{messages.outcome_line(True)}"


@pytest.mark.asyncio
async def test_an_unavailable_explanation_status_omits_the_spiega_button() -> None:
    double = _FlowServiceDouble(
        question=_question(), correct=True, explanation_status=ExplanationStatus.UNAVAILABLE
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    call = query.edit_message_text.call_args
    assert _button_texts(call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]


@pytest.mark.asyncio
async def test_an_uncached_explanation_status_shows_the_spiega_button() -> None:
    """The omission predicate is `is not UNAVAILABLE`, so UNCACHED must still show it.

    This is the third, most on-demand-relevant status: a genuine cache miss that
    `POST /label` (not shown yet) would compute live once the user taps "Spiega".
    """
    double = _FlowServiceDouble(
        question=_question(), correct=True, explanation_status=ExplanationStatus.UNCACHED
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:1")

    await handle_answer_callback(update, context)

    call = query.edit_message_text.call_args
    assert _button_texts(call.kwargs["reply_markup"]) == ["Spiega", "Prossima domanda ▶"]


@pytest.mark.asyncio
async def test_a_valid_answer_on_a_photo_message_edits_the_caption() -> None:
    context = _context(_FlowServiceDouble(question=_question(), correct=False))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0001:0", has_photo=True)

    await handle_answer_callback(update, context)

    query.edit_message_caption.assert_awaited_once()
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_stale_answer_gets_a_notice_and_no_edit() -> None:
    context = _context(_FlowServiceDouble(question=_question(), raise_stale=True))
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{ANSWER_CALLBACK_PREFIX}0002:1")

    await handle_answer_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    query.edit_message_text.assert_not_awaited()
    query.edit_message_caption.assert_not_awaited()


@pytest.mark.asyncio
async def test_explain_callback_shows_a_loading_line_then_the_explanation() -> None:
    """Spec 0017 FR-3, AD-13: optimistic edit first, then the real explanation.

    Spec 0018 bot UX: the final keyboard also offers "🇷🇺 Traduci", and the shown
    Italian text is stashed on the session as `last_explanation`.
    """
    explanation = QuizExplanation(status=ExplanationOutcome.EXPLAINED, explanation="perché...")
    double = _FlowServiceDouble(explanation=explanation, question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(
        f"{EXPLAIN_CALLBACK_PREFIX}0001:1", text="❌ Risposta sbagliata."
    )

    await handle_explain_callback(update, context)

    assert query.edit_message_text.await_count == 2
    first_call, second_call = query.edit_message_text.await_args_list
    assert messages.LOADING_EXPLANATION_LINE in first_call.kwargs["text"]
    assert "❌ Risposta sbagliata." in first_call.kwargs["text"]
    assert _button_texts(first_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]
    assert "perché..." in second_call.kwargs["text"]
    assert "❌ Risposta sbagliata." in second_call.kwargs["text"]
    assert double.explanation_request_calls == [("0001", _TELEGRAM_USER_ID, True)]
    assert _button_texts(second_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    assert context.user_data["session"].last_explanation == "perché..."


@pytest.mark.asyncio
async def test_explain_callback_on_a_photo_message_edits_the_caption_twice() -> None:
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1", has_photo=True)

    await handle_explain_callback(update, context)

    assert query.edit_message_caption.await_count == 2
    query.edit_message_text.assert_not_awaited()
    assert context.user_data["session"].last_explanation == "perché..."


@pytest.mark.asyncio
async def test_explain_callback_on_a_photo_sends_an_oversized_explanation_separately() -> None:
    """Telegram caps a caption at 1024 chars: an explanation past it goes out as a message.

    The loading line still fits (caption + 26 chars), so it is shown; the final edit then
    reverts the caption to the question/outcome text and keeps the keyboard (so "Traduci"
    still works), while the explanation travels as its own message.
    """
    long_caption = "Domanda? " + "x" * 950
    long_explanation = "y" * 100
    double = _FlowServiceDouble(
        question=_question(),
        explanation=QuizExplanation(
            status=ExplanationOutcome.EXPLAINED, explanation=long_explanation
        ),
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(
        f"{EXPLAIN_CALLBACK_PREFIX}0001:1", has_photo=True, text=long_caption
    )

    await handle_explain_callback(update, context)

    first_call, second_call = query.edit_message_caption.await_args_list
    assert first_call.kwargs["caption"] == f"{long_caption}\n\n{messages.LOADING_EXPLANATION_LINE}"
    assert second_call.kwargs["caption"] == long_caption
    assert _button_texts(second_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == long_explanation
    assert context.user_data["session"].last_explanation == long_explanation


@pytest.mark.asyncio
async def test_explain_callback_insufficient_knowledge_shows_the_fallback_line() -> None:
    """Spec 0018 bot UX: nothing to translate, so "Traduci" is omitted, mirroring "Spiega"."""
    explanation = QuizExplanation(
        status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE, explanation=None
    )
    double = _FlowServiceDouble(explanation=explanation, question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1")

    await handle_explain_callback(update, context)

    _, second_call = query.edit_message_text.await_args_list
    assert messages.NO_EXPLANATION_LINE in second_call.kwargs["text"]
    assert _button_texts(second_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]
    assert context.user_data["session"].last_explanation is None


@pytest.mark.asyncio
async def test_a_stale_explain_tap_gets_a_notice_and_no_edit_at_all() -> None:
    """The optimistic edit must not fire for a question the chat has moved past (AD-13)."""
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0002:1")

    await handle_explain_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    query.edit_message_text.assert_not_awaited()
    query.edit_message_caption.assert_not_awaited()
    assert double.explanation_request_calls == []


@pytest.mark.asyncio
async def test_translate_callback_replaces_the_text_with_a_bilingual_message() -> None:
    """Spec 0018 bot UX: loading edit, then the Italian text plus the Russian line."""
    double = _FlowServiceDouble(question=_question(), translation="Перевод.")
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(
        f"{TRANSLATE_CALLBACK_PREFIX}0001", text="❌ Risposta sbagliata.\n\nperché..."
    )

    await handle_translate_callback(update, context)

    assert query.edit_message_text.await_count == 2
    first_call, second_call = query.edit_message_text.await_args_list
    assert messages.LOADING_TRANSLATION_LINE in first_call.kwargs["text"]
    assert _button_texts(first_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]
    assert "❌ Risposta sbagliata.\n\nperché..." in second_call.kwargs["text"]
    assert "🇷🇺 Перевод." in second_call.kwargs["text"]
    assert _button_texts(second_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]
    assert double.translate_request_calls == [("perché...", _TELEGRAM_USER_ID)]
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_translate_callback_on_a_photo_message_sends_a_separate_message() -> None:
    """The 1024-char caption limit means the translation is a new message, not an append."""
    double = _FlowServiceDouble(question=_question(), translation="Перевод.")
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(
        f"{TRANSLATE_CALLBACK_PREFIX}0001",
        has_photo=True,
        text="❌ Risposta sbagliata.\n\nperché...",
    )

    await handle_translate_callback(update, context)

    assert query.edit_message_caption.await_count == 2
    final_call = query.edit_message_caption.await_args_list[1]
    assert final_call.kwargs["caption"] == "❌ Risposta sbagliata.\n\nperché..."
    query.edit_message_text.assert_not_awaited()
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == "🇷🇺 Перевод."


@pytest.mark.asyncio
async def test_translate_callback_a_stale_tap_gets_a_notice_and_no_edit() -> None:
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(f"{TRANSLATE_CALLBACK_PREFIX}0002")

    await handle_translate_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    query.edit_message_text.assert_not_awaited()
    query.edit_message_caption.assert_not_awaited()
    assert double.translate_request_calls == []


@pytest.mark.asyncio
async def test_translate_callback_with_no_stored_explanation_is_also_stale() -> None:
    """A session that never had `handle_explain_callback` run for it has nothing to translate."""
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{TRANSLATE_CALLBACK_PREFIX}0001")

    await handle_translate_callback(update, context)

    query.answer.assert_awaited_once()
    assert "non è più valida" in query.answer.call_args.args[0]
    assert double.translate_request_calls == []


@pytest.mark.asyncio
async def test_a_failed_translation_reverts_the_edit_and_sends_an_error_notice() -> None:
    """No native alert is possible here (the answer() slot is spent on the loading edit)."""
    double = _FlowServiceDouble(question=_question(), raise_translate_error=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(
        f"{TRANSLATE_CALLBACK_PREFIX}0001", text="❌ Risposta sbagliata.\n\nperché..."
    )

    await handle_translate_callback(update, context)

    assert query.edit_message_text.await_count == 2
    _, second_call = query.edit_message_text.await_args_list
    assert second_call.kwargs["text"] == "❌ Risposta sbagliata.\n\nperché..."
    assert _button_texts(second_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == messages.TRANSLATION_ERROR_MESSAGE


@pytest.mark.asyncio
async def test_a_failed_translation_on_a_photo_message_reverts_the_caption() -> None:
    """Photo + failure: the caption revert must use edit_message_caption, never edit_message_text.

    Picking the wrong edit method here is a runtime Telegram BadRequest
    ("there is no text in the message to edit"), not a type error.
    """
    double = _FlowServiceDouble(question=_question(), raise_translate_error=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(
        f"{TRANSLATE_CALLBACK_PREFIX}0001",
        has_photo=True,
        text="❌ Risposta sbagliata.\n\nperché...",
    )

    await handle_translate_callback(update, context)

    assert query.edit_message_caption.await_count == 2
    query.edit_message_text.assert_not_awaited()
    final_call = query.edit_message_caption.await_args_list[1]
    assert final_call.kwargs["caption"] == "❌ Risposta sbagliata.\n\nperché..."
    assert _button_texts(final_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == messages.TRANSLATION_ERROR_MESSAGE


@pytest.mark.asyncio
async def test_stop_shows_the_summary_and_clears_the_session() -> None:
    double = _FlowServiceDouble(
        question=_question(), summary=SessionSummary(answered=5, correct=3)
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="abc", index=4, current_question_number="0001")

    await stop_command(_update(), context)

    assert double.summary_calls == [(_TELEGRAM_USER_ID, "abc")]
    text = context.bot.send_message.call_args.kwargs["text"]
    assert "5" in text and "3" in text
    assert "session" not in context.user_data


@pytest.mark.asyncio
async def test_stop_with_no_active_session_sends_a_notice_and_calls_nothing() -> None:
    double = _FlowServiceDouble(question=_question())
    context = _context(double)

    await stop_command(_update(), context)

    assert double.summary_calls == []
    text = context.bot.send_message.call_args.kwargs["text"]
    assert "nessuna sessione" in text.lower()


@pytest.mark.asyncio
async def test_stop_does_not_clear_the_session_when_the_summary_call_fails() -> None:
    context = _context(_FlowServiceDouble(question=_question(), raise_summary_error=True))
    context.user_data["session"] = QuizSession(seed="abc", index=4, current_question_number="0001")

    with pytest.raises(QuizApiError):
        await stop_command(_update(), context)

    assert "session" in context.user_data, (
        "D-16: a failed summary call must not strand the user without their session"
    )
