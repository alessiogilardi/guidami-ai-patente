"""Telegram handlers are thin controllers over QuizFlowService (AD-5, spec 0016/0017/0018)."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guidami_ai_patente_bot import container, messages
from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus, SessionMode
from guidami_ai_patente_bot.exceptions import (
    QuizApiError,
    SessionCompletedError,
    StaleQuestionError,
)
from guidami_ai_patente_bot.handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    EXPLAIN_CALLBACK_PREFIX,
    TOPIC_CALLBACK_PREFIX,
    TRANSLATE_CALLBACK_PREFIX,
    _glossary_block,
    argomento_command,
    handle_answer_callback,
    handle_explain_callback,
    handle_next_callback,
    handle_topic_callback,
    handle_translate_callback,
    quiz_command,
    ripasso_command,
    start_command,
    statistiche_command,
    stop_command,
)
from guidami_ai_patente_bot.models import (
    CitedGlossaryTerm,
    QuizExplanation,
    QuizQuestion,
    QuizSession,
    SessionSummary,
    TopicMastery,
    TopicSummary,
    UserStatistics,
    WrongQuestion,
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
    translate_request_calls: list[tuple[str, int, tuple[CitedGlossaryTerm, ...]]] = field(
        default_factory=list
    )
    registration_calls: list[int] = field(default_factory=list)
    summary: SessionSummary = field(
        default_factory=lambda: SessionSummary(
            answered=0, correct=0, by_topic=[], wrong_questions=[]
        )
    )
    raise_summary_error: bool = False
    summary_calls: list[tuple[int, str]] = field(default_factory=list)
    start_completes: bool = False
    complete_on_propose: bool = False
    propose_error: bool = False
    statistics: UserStatistics = field(
        default_factory=lambda: UserStatistics(
            answered=0, seen=0, bank_total=0, mastered=0, in_review=0, topics=[]
        )
    )
    start_calls: list[tuple[SessionMode, str | None, int]] = field(default_factory=list)

    async def start_session(
        self, mode: SessionMode, topic: str | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        self.start_calls.append((mode, topic, telegram_user_id))
        if self.start_completes:
            raise SessionCompletedError()
        new_session = QuizSession(
            seed="fresh-seed",
            index=0,
            current_question_number=self.question.number,
            mode=mode,
            topic=topic,
        )
        return self.question, new_session

    async def get_statistics(self, telegram_user_id: int) -> UserStatistics:
        return self.statistics

    async def propose_question(
        self, session: QuizSession | None, telegram_user_id: int
    ) -> tuple[QuizQuestion, QuizSession]:
        self.propose_calls.append(telegram_user_id)
        if self.propose_error:
            raise QuizApiError("boom")
        if self.complete_on_propose:
            raise SessionCompletedError()
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

    async def handle_translation_request(
        self, text: str, telegram_user_id: int, hints: tuple[CitedGlossaryTerm, ...]
    ) -> str:
        self.translate_request_calls.append((text, telegram_user_id, hints))
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
        if target_type is BotConfig:
            return SimpleNamespace(topic_label_max_chars=40)
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


def test_glossary_block_renders_one_line_per_hint_in_order() -> None:
    hints = (
        CitedGlossaryTerm(term="banchina", definition="Parte della strada...", term_ru="обочина"),
        CitedGlossaryTerm(
            term="carreggiata", definition="Parte della strada...", term_ru="проезжая часть"
        ),
    )
    block = _glossary_block(hints)
    lines = block.splitlines()
    assert lines[0] == "📖 banchina — Parte della strada..."
    assert lines[1] == "📖 carreggiata — Parte della strada..."


def test_glossary_block_is_empty_string_for_no_hints() -> None:
    assert _glossary_block(()) == ""


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
    for command in ("/quiz", "/stop", "/start", "/statistiche", "/ripasso", "/argomento"):
        assert command in text


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
async def test_explain_callback_renders_vocabulary_and_glossary_around_the_explanation() -> None:
    """Spec 0020 FR-7, FR-8: three sections, in order, blank ones simply omitted."""
    hints = (
        CitedGlossaryTerm(term="banchina", definition="Parte della strada...", term_ru="обочина"),
    )
    explanation = QuizExplanation(
        status=ExplanationOutcome.EXPLAINED,
        explanation="perché...",
        term_explanation="Vocabolario: banchina è il margine della strada.",
        translation_hints=hints,
    )
    double = _FlowServiceDouble(explanation=explanation, question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(
        f"{EXPLAIN_CALLBACK_PREFIX}0001:1", text="❌ Risposta sbagliata."
    )

    await handle_explain_callback(update, context)

    _, second_call = query.edit_message_text.await_args_list
    text = second_call.kwargs["text"]
    vocab_index = text.index("Vocabolario: banchina è il margine della strada.")
    explanation_index = text.index("perché...")
    glossary_index = text.index("📖 banchina — Parte della strada...")
    assert vocab_index < explanation_index < glossary_index
    assert context.user_data["session"].last_explanation == (
        "Vocabolario: banchina è il margine della strada.\n\n"
        "perché...\n\n"
        "📖 banchina — Parte della strada..."
    )
    assert context.user_data["session"].last_explanation_hints == hints


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
async def test_explain_callback_oversized_message_includes_vocabulary_and_glossary() -> None:
    """The overflow follow-up message must send the full body, not just the legal explanation.

    Regression test for a fix applied in a grilling round (spec 0020, 2026-09-23): this
    path used to send the narrower `explanation_line` as the follow-up message, so a long
    vocabulary paragraph or glossary block was silently dropped whenever a message was
    long enough to trigger the overflow branch — which a vocabulary section and glossary
    block make more likely, not less.
    """
    long_caption = "Domanda? " + "x" * 950
    hints = (
        CitedGlossaryTerm(term="banchina", definition="Parte della strada...", term_ru="обочина"),
    )
    double = _FlowServiceDouble(
        question=_question(),
        explanation=QuizExplanation(
            status=ExplanationOutcome.EXPLAINED,
            explanation="perché...",
            term_explanation="Vocabolario: banchina è il margine della strada.",
            translation_hints=hints,
        ),
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(
        f"{EXPLAIN_CALLBACK_PREFIX}0001:1", has_photo=True, text=long_caption
    )

    await handle_explain_callback(update, context)

    context.bot.send_message.assert_awaited_once()
    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "Vocabolario: banchina è il margine della strada." in sent_text
    assert "perché..." in sent_text
    assert "📖 banchina — Parte della strada..." in sent_text
    assert context.user_data["session"].last_explanation == sent_text
    assert context.user_data["session"].last_explanation_hints == hints


@pytest.mark.asyncio
async def test_explain_callback_on_a_text_message_sends_an_oversized_explanation_separately() -> (
    None
):
    """Fix #5: the same overflow guard as the photo path, for Telegram's 4096-char text limit.

    `term_explanation` + the legal explanation + a glossary block can realistically push a
    text (non-photo) message's combined body past 4096 chars; before this fix nothing
    caught that, so `edit_message_text` would raise `BadRequest` and strand the message
    in its loading state.
    """
    long_text = "Domanda? " + "x" * 4070
    long_explanation = "y" * 100
    double = _FlowServiceDouble(
        question=_question(),
        explanation=QuizExplanation(
            status=ExplanationOutcome.EXPLAINED, explanation=long_explanation
        ),
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1", text=long_text)

    await handle_explain_callback(update, context)

    first_call, second_call = query.edit_message_text.await_args_list
    assert first_call.kwargs["text"] == f"{long_text}\n\n{messages.LOADING_EXPLANATION_LINE}"
    assert second_call.kwargs["text"] == long_text
    assert _button_texts(second_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == long_explanation
    assert context.user_data["session"].last_explanation == long_explanation


@pytest.mark.asyncio
async def test_explain_callback_oversized_text_message_includes_vocabulary_and_glossary() -> None:
    """The text-path overflow follow-up must also carry the full body, not just the legal line."""
    long_text = "Domanda? " + "x" * 4070
    hints = (
        CitedGlossaryTerm(term="banchina", definition="Parte della strada...", term_ru="обочина"),
    )
    double = _FlowServiceDouble(
        question=_question(),
        explanation=QuizExplanation(
            status=ExplanationOutcome.EXPLAINED,
            explanation="perché...",
            term_explanation="Vocabolario: banchina è il margine della strada.",
            translation_hints=hints,
        ),
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1", text=long_text)

    await handle_explain_callback(update, context)

    context.bot.send_message.assert_awaited_once()
    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "Vocabolario: banchina è il margine della strada." in sent_text
    assert "perché..." in sent_text
    assert "📖 banchina — Parte della strada..." in sent_text
    assert context.user_data["session"].last_explanation == sent_text
    assert context.user_data["session"].last_explanation_hints == hints


@pytest.mark.asyncio
async def test_explain_callback_oversized_follow_up_is_split_across_several_messages() -> None:
    """A body over 4096 chars on its own must be delivered in full, chunked, never dropped.

    Reproduces the gap left by the prior fix wave: `handle_explain_callback`'s overflow
    follow-up used a single unguarded `send_message` call, so a long `term_explanation`
    plus the legal explanation plus a glossary block (realistic combined sizes per the
    module-level `_TEXT_LIMIT` comment) could itself exceed Telegram's 4096-char text-
    message limit and raise `BadRequest`.
    """
    term_explanation = "V" * 2000
    explanation_text = "E" * 2000
    hint = CitedGlossaryTerm(term="termine", definition="D" * 200, term_ru="термин")
    glossary_block = _glossary_block((hint,))
    body = "\n\n".join([term_explanation, explanation_text, glossary_block])
    assert len(body) > 4096, "the test body must actually require chunking"

    double = _FlowServiceDouble(
        question=_question(),
        explanation=QuizExplanation(
            status=ExplanationOutcome.EXPLAINED,
            explanation=explanation_text,
            term_explanation=term_explanation,
            translation_hints=(hint,),
        ),
    )
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1", text="Domanda?")

    await handle_explain_callback(update, context)

    sent_texts = [call.kwargs["text"] for call in context.bot.send_message.await_args_list]
    assert len(sent_texts) > 1, "a body this long must be split across multiple send_message calls"
    assert all(len(text) <= 4096 for text in sent_texts)
    assert "\n\n".join(sent_texts) == body, "no content may be dropped, only split further"
    _, second_call = query.edit_message_text.await_args_list
    assert second_call.kwargs["text"] == "Domanda?"


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
async def test_explain_callback_insufficient_knowledge_with_term_explanation_offers_traduci() -> (
    None
):
    """Fix #6: AD-1's two stages are independent.

    A refused legal stage still has a real vocabulary explanation worth translating,
    so "Traduci" must not be omitted.
    """
    explanation = QuizExplanation(
        status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE,
        explanation=None,
        term_explanation="Vocabolario: banchina è il margine della strada.",
    )
    double = _FlowServiceDouble(explanation=explanation, question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="s", index=0, current_question_number="0001")
    update, query = _callback_update(f"{EXPLAIN_CALLBACK_PREFIX}0001:1")

    await handle_explain_callback(update, context)

    _, second_call = query.edit_message_text.await_args_list
    assert messages.NO_EXPLANATION_LINE in second_call.kwargs["text"]
    assert "Vocabolario: banchina è il margine della strada." in second_call.kwargs["text"]
    assert _button_texts(second_call.kwargs["reply_markup"]) == [
        "🇷🇺 Traduci",
        "Prossima domanda ▶",
    ]
    assert context.user_data["session"].last_explanation is not None
    assert "Vocabolario" in context.user_data["session"].last_explanation


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
    assert double.translate_request_calls == [("perché...", _TELEGRAM_USER_ID, ())]
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_translate_callback_forwards_the_stored_hints() -> None:
    """Spec 0020 FR-7: the hints shown alongside the explanation travel with a "Traduci" tap."""
    hints = (
        CitedGlossaryTerm(term="banchina", definition="Parte della strada...", term_ru="обочина"),
    )
    double = _FlowServiceDouble(question=_question(), translation="Перевод.")
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s",
        index=0,
        current_question_number="0001",
        last_explanation="perché...",
        last_explanation_hints=hints,
    )
    update, query = _callback_update(
        f"{TRANSLATE_CALLBACK_PREFIX}0001", text="❌ Risposta sbagliata.\n\nperché..."
    )

    await handle_translate_callback(update, context)

    assert double.translate_request_calls == [("perché...", _TELEGRAM_USER_ID, hints)]


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
async def test_translate_callback_on_text_sends_an_oversized_translation_separately() -> None:
    """Fix #5: "Traduci" roughly doubles the body, so the text path needs the same guard."""
    long_pre_text = "Domanda? " + "x" * 4070
    long_translation = "y" * 100
    double = _FlowServiceDouble(question=_question(), translation=long_translation)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(f"{TRANSLATE_CALLBACK_PREFIX}0001", text=long_pre_text)

    await handle_translate_callback(update, context)

    assert query.edit_message_text.await_count == 2
    _, second_call = query.edit_message_text.await_args_list
    assert second_call.kwargs["text"] == long_pre_text
    assert _button_texts(second_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.call_args.kwargs["text"] == f"🇷🇺 {long_translation}"


@pytest.mark.asyncio
async def test_translate_callback_loading_edit_never_exceeds_the_text_limit() -> None:
    """The loading edit itself must respect 4096 chars, not just the final edit.

    `pre_text` can already sit at Telegram's 4096-char limit (a non-overflowing
    `/explanation` message, per `handle_explain_callback`'s own guard). Appending
    `LOADING_TRANSLATION_LINE` to that would push the *loading* `edit_message_text`
    call itself past the limit — a gap the prior fix wave's guard (on the final edit
    only) never covered. The loading line must be dropped rather than sent oversized.
    """
    long_pre_text = "Domanda? " + "x" * 4087
    assert len(long_pre_text) == 4096, "pre_text must sit exactly at the limit"
    loading_text = f"{long_pre_text}\n\n{messages.LOADING_TRANSLATION_LINE}"
    assert len(loading_text) > 4096, "combining with the loading line must actually overflow"

    double = _FlowServiceDouble(question=_question(), translation="Перевод.")
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="s", index=0, current_question_number="0001", last_explanation="perché..."
    )
    update, query = _callback_update(f"{TRANSLATE_CALLBACK_PREFIX}0001", text=long_pre_text)

    await handle_translate_callback(update, context)

    for call in query.edit_message_text.await_args_list:
        assert len(call.kwargs["text"]) <= 4096
    first_call = query.edit_message_text.await_args_list[0]
    assert first_call.kwargs["text"] == long_pre_text, (
        "the loading line must be dropped, not appended, once it would overflow"
    )
    assert _button_texts(first_call.kwargs["reply_markup"]) == ["Prossima domanda ▶"]


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
    summary = SessionSummary(
        answered=5,
        correct=3,
        by_topic=[TopicSummary(topic="Precedenza", answered=5, correct=3)],
        wrong_questions=[WrongQuestion(number="0001", text="Domanda?")],
    )
    double = _FlowServiceDouble(question=_question(), summary=summary)
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="abc", index=4, current_question_number="0001")

    await stop_command(_update(), context)

    assert double.summary_calls == [(_TELEGRAM_USER_ID, "abc")]
    text = context.bot.send_message.call_args.kwargs["text"]
    assert text == messages.summary_message(summary)
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


@pytest.mark.asyncio
async def test_statistiche_sends_the_rendered_statistics() -> None:
    stats = UserStatistics(
        answered=5,
        seen=4,
        bank_total=10,
        mastered=2,
        in_review=1,
        topics=[
            TopicMastery(topic="Segnali", seen=4, mastered=2, total=9, insufficient_data=False)
        ],
    )
    context = _context(_FlowServiceDouble(question=_question(), statistics=stats))

    await statistiche_command(_update(), context)

    text = context.bot.send_message.call_args.kwargs["text"]
    assert text == messages.statistics_message(stats, 40)


@pytest.mark.asyncio
async def test_a_long_statistics_message_is_split_into_chunks_within_the_limit() -> None:
    topics = [
        TopicMastery(topic=f"Argomento {i}", seen=1, mastered=0, total=9, insufficient_data=True)
        for i in range(700)
    ]
    stats = UserStatistics(
        answered=1, seen=1, bank_total=10, mastered=0, in_review=0, topics=topics
    )
    context = _context(_FlowServiceDouble(question=_question(), statistics=stats))

    await statistiche_command(_update(), context)

    chunks = [call.kwargs["text"] for call in context.bot.send_message.call_args_list]
    assert len(chunks) > 1
    assert all(len(chunk) <= 4096 for chunk in chunks)


@pytest.mark.asyncio
async def test_ripasso_with_nothing_to_review_replies_and_leaves_no_session() -> None:
    double = _FlowServiceDouble(question=_question(), start_completes=True)
    context = _context(double)

    await ripasso_command(_update(), context)

    assert double.start_calls == [(SessionMode.REVIEW, None, _TELEGRAM_USER_ID)]
    assert context.bot.send_message.call_args.kwargs["text"] == messages.NO_REVIEW_MESSAGE
    assert "session" not in context.user_data


@pytest.mark.asyncio
async def test_ripasso_with_nothing_to_review_clears_a_pending_session() -> None:
    double = _FlowServiceDouble(question=_question(), start_completes=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="old", index=2, current_question_number="0009")

    await ripasso_command(_update(), context)

    assert "session" not in context.user_data
    assert context.bot.send_message.call_args.kwargs["text"] == messages.NO_REVIEW_MESSAGE


@pytest.mark.asyncio
async def test_ripasso_replaces_a_pending_random_session_with_a_review_session() -> None:
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="old", index=2, current_question_number="0009")

    await ripasso_command(_update(), context)

    session = context.user_data["session"]
    assert session.mode is SessionMode.REVIEW
    assert session.seed != "old"
    assert session.current_question_number == "0001"
    sent = context.bot.send_message.call_args.kwargs
    assert sent["text"] == "Domanda?"
    assert _button_texts(sent["reply_markup"]) == ["Vero", "Falso"]


@pytest.mark.asyncio
async def test_next_on_a_completed_review_shows_completion_summary_and_clears_session() -> None:
    summary = SessionSummary(answered=2, correct=1, by_topic=[], wrong_questions=[])
    double = _FlowServiceDouble(question=_question(), complete_on_propose=True, summary=summary)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="rev", index=1, current_question_number="0001", mode=SessionMode.REVIEW
    )
    update, _ = _callback_update("quiz:next")

    await handle_next_callback(update, context)

    texts = [call.kwargs["text"] for call in context.bot.send_message.call_args_list]
    assert texts == [messages.REVIEW_COMPLETED_MESSAGE, messages.summary_message(summary)]
    assert double.summary_calls == [(_TELEGRAM_USER_ID, "rev")]
    assert "session" not in context.user_data


@pytest.mark.asyncio
async def test_stop_and_a_second_ripasso_work_cleanly_after_completion() -> None:
    double = _FlowServiceDouble(question=_question(), complete_on_propose=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="rev", index=1, current_question_number="0001", mode=SessionMode.REVIEW
    )
    update, _ = _callback_update("quiz:next")
    await handle_next_callback(update, context)

    await stop_command(_update(), context)
    assert context.bot.send_message.call_args.kwargs["text"] == messages.NO_SESSION_MESSAGE

    await ripasso_command(_update(), context)
    assert context.user_data["session"].mode is SessionMode.REVIEW


def _topic_stats(*topics: TopicMastery) -> UserStatistics:
    return UserStatistics(
        answered=5, seen=4, bank_total=10, mastered=2, in_review=0, topics=list(topics)
    )


def _keyboard_buttons(sent: dict) -> list:
    return [button for row in sent["reply_markup"].inline_keyboard for button in row]


_RANKED = TopicMastery(
    topic="Segnali; dettagli", seen=4, mastered=2, total=9, insufficient_data=False
)
_EXPLORE = TopicMastery(topic="Precedenza", seen=1, mastered=0, total=7, insufficient_data=True)


@pytest.mark.asyncio
async def test_argomento_callback_data_never_carries_the_topic_name() -> None:
    long_topic = "Segnali di pericolo " + "x" * 325
    assert len(long_topic.encode()) == 345
    stats = _topic_stats(
        TopicMastery(topic=long_topic, seen=4, mastered=2, total=9, insufficient_data=False)
    )
    context = _context(_FlowServiceDouble(question=_question(), statistics=stats))

    await argomento_command(_update(), context)

    buttons = _keyboard_buttons(context.bot.send_message.call_args.kwargs)
    data = buttons[0].callback_data
    assert len(data.encode()) <= 64
    assert "Segnali" not in data
    assert data.startswith(TOPIC_CALLBACK_PREFIX)
    assert context.user_data["topic_choices"] == [long_topic]
    assert data == f"topic:{context.user_data['topic_token']}:0"


@pytest.mark.asyncio
async def test_argomento_buttons_use_short_labels_with_percent_or_seen_total_in_order() -> None:
    stats = _topic_stats(_RANKED, _EXPLORE)
    context = _context(_FlowServiceDouble(question=_question(), statistics=stats))

    await argomento_command(_update(), context)

    buttons = _keyboard_buttons(context.bot.send_message.call_args.kwargs)
    assert [b.text for b in buttons] == ["Segnali: 50%", "Precedenza: 1/7"]
    assert context.user_data["topic_choices"] == ["Segnali; dettagli", "Precedenza"]


@pytest.mark.asyncio
async def test_a_newer_keyboard_overwrites_the_token() -> None:
    context = _context(_FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED)))
    await argomento_command(_update(), context)
    first = context.user_data["topic_token"]
    await argomento_command(_update(), context)
    assert context.user_data["topic_token"] != first
    assert len(context.user_data["topic_token"]) == 8


@pytest.mark.asyncio
async def test_tapping_an_old_keyboard_is_stale_and_starts_nothing() -> None:
    double = _FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED))
    context = _context(double)
    await argomento_command(_update(), context)
    old_data = _keyboard_buttons(context.bot.send_message.call_args.kwargs)[0].callback_data
    await argomento_command(_update(), context)
    existing = QuizSession(seed="old", index=2, current_question_number="0009")
    context.user_data["session"] = existing
    context.bot.send_message.reset_mock()
    update, query = _callback_update(old_data)

    await handle_topic_callback(update, context)

    query.answer.assert_awaited_once_with(messages.STALE_NOTICE)
    assert double.start_calls == []
    assert context.user_data["session"] is existing
    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_a_valid_tap_starts_a_topic_session_and_replaces_a_random_one() -> None:
    double = _FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED, _EXPLORE))
    context = _context(double)
    await argomento_command(_update(), context)
    buttons = _keyboard_buttons(context.bot.send_message.call_args.kwargs)
    # The button label is the short "Segnali: 50%", so passing the label on would fail below.
    assert buttons[0].text.startswith("Segnali:")
    data = buttons[0].callback_data
    context.user_data["session"] = QuizSession(seed="old", index=2, current_question_number="0009")
    update, query = _callback_update(data)

    await handle_topic_callback(update, context)

    query.answer.assert_awaited_once_with()
    assert double.start_calls == [(SessionMode.TOPIC, "Segnali; dettagli", _TELEGRAM_USER_ID)]
    session = context.user_data["session"]
    assert session.mode is SessionMode.TOPIC
    assert session.topic == "Segnali; dettagli"
    assert session.seed != "old"
    assert context.bot.send_message.call_args.kwargs["text"] == "Domanda?"


@pytest.mark.asyncio
async def test_a_second_tap_of_the_same_keyboard_is_stale_and_keeps_the_session() -> None:
    double = _FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED))
    context = _context(double)
    await argomento_command(_update(), context)
    data = _keyboard_buttons(context.bot.send_message.call_args.kwargs)[0].callback_data
    first_update, _ = _callback_update(data)
    await handle_topic_callback(first_update, context)
    started = context.user_data["session"]
    context.bot.send_message.reset_mock()
    second_update, second_query = _callback_update(data)

    await handle_topic_callback(second_update, context)

    second_query.answer.assert_awaited_once_with(messages.STALE_NOTICE)
    assert len(double.start_calls) == 1
    assert context.user_data["session"] is started
    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_argomento_with_no_topics_replies_with_plain_text_and_no_keyboard() -> None:
    context = _context(_FlowServiceDouble(question=_question(), statistics=_topic_stats()))

    await argomento_command(_update(), context)

    sent = context.bot.send_message.call_args.kwargs
    assert sent["text"] == messages.NO_TOPICS_MESSAGE
    assert "reply_markup" not in sent


@pytest.mark.asyncio
async def test_a_tap_with_missing_choices_is_stale() -> None:
    double = _FlowServiceDouble(question=_question())
    context = _context(double)
    update, query = _callback_update("topic:abcd1234:0")

    await handle_topic_callback(update, context)

    query.answer.assert_awaited_once_with(messages.STALE_NOTICE)
    assert double.start_calls == []
    assert "session" not in context.user_data


@pytest.mark.asyncio
@pytest.mark.parametrize("index", ["5", "-1", "x"])
async def test_a_tap_with_a_bad_index_is_stale(index: str) -> None:
    double = _FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED))
    context = _context(double)
    await argomento_command(_update(), context)
    token = context.user_data["topic_token"]
    update, query = _callback_update(f"topic:{token}:{index}")

    await handle_topic_callback(update, context)

    query.answer.assert_awaited_once_with(messages.STALE_NOTICE)
    assert double.start_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("template", ["topic:{token}", "topic:"])
async def test_a_tap_with_a_missing_field_is_stale(template: str) -> None:
    double = _FlowServiceDouble(question=_question(), statistics=_topic_stats(_RANKED))
    context = _context(double)
    await argomento_command(_update(), context)
    update, query = _callback_update(template.format(token=context.user_data["topic_token"]))

    await handle_topic_callback(update, context)

    query.answer.assert_awaited_once_with(messages.STALE_NOTICE)
    assert double.start_calls == []
    assert "session" not in context.user_data


@pytest.mark.asyncio
async def test_a_tap_on_an_empty_topic_clears_the_session_and_announces_completion() -> None:
    double = _FlowServiceDouble(
        question=_question(), statistics=_topic_stats(_RANKED), start_completes=True
    )
    context = _context(double)
    await argomento_command(_update(), context)
    data = _keyboard_buttons(context.bot.send_message.call_args.kwargs)[0].callback_data
    context.user_data["session"] = QuizSession(seed="old", index=2, current_question_number="0009")
    update, _ = _callback_update(data)

    await handle_topic_callback(update, context)

    assert "session" not in context.user_data
    assert context.bot.send_message.call_args.kwargs["text"] == messages.TOPIC_COMPLETED_MESSAGE


@pytest.mark.asyncio
async def test_next_on_an_exhausted_topic_completes_summarizes_and_clears() -> None:
    summary = SessionSummary(answered=2, correct=1, by_topic=[], wrong_questions=[])
    double = _FlowServiceDouble(question=_question(), complete_on_propose=True, summary=summary)
    context = _context(double)
    context.user_data["session"] = QuizSession(
        seed="top", index=1, current_question_number="0001", mode=SessionMode.TOPIC, topic="X"
    )
    update, _ = _callback_update("quiz:next")

    await handle_next_callback(update, context)

    texts = [call.kwargs["text"] for call in context.bot.send_message.call_args_list]
    assert texts == [messages.TOPIC_COMPLETED_MESSAGE, messages.summary_message(summary)]
    assert "session" not in context.user_data


@pytest.mark.asyncio
async def test_random_mode_api_failures_still_propagate_without_a_completion_message() -> None:
    double = _FlowServiceDouble(question=_question(), propose_error=True)
    context = _context(double)
    context.user_data["session"] = QuizSession(seed="r", index=1, current_question_number="0001")
    update, _ = _callback_update("quiz:next")

    with pytest.raises(QuizApiError):
        await handle_next_callback(update, context)

    context.bot.send_message.assert_not_called()
    assert "session" in context.user_data
