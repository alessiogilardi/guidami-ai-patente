"""Telegram update handlers: thin controllers over QuizFlowService (AD-5, spec 0016 AD-11)."""

from io import BytesIO
from typing import cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from guidami_ai_patente_bot import container, messages
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus
from guidami_ai_patente_bot.exceptions import QuizApiError, StaleQuestionError
from guidami_ai_patente_bot.models import QuizSession
from guidami_ai_patente_bot.services import QuizFlowService

ANSWER_CALLBACK_PREFIX = "quiz:answer:"
EXPLAIN_CALLBACK_PREFIX = "quiz:explain:"
TRANSLATE_CALLBACK_PREFIX = "quiz:translate:"
NEXT_CALLBACK_DATA = "quiz:next"

_NEXT_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Prossima domanda ▶", callback_data=NEXT_CALLBACK_DATA)]]
)


def _answer_callback_data(number: str, answer: bool) -> str:
    return f"{ANSWER_CALLBACK_PREFIX}{number}:{int(answer)}"


def _explain_callback_data(number: str, answer: bool) -> str:
    return f"{EXPLAIN_CALLBACK_PREFIX}{number}:{int(answer)}"


def _translate_callback_data(number: str) -> str:
    return f"{TRANSLATE_CALLBACK_PREFIX}{number}"


def _question_keyboard(number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Vero", callback_data=_answer_callback_data(number, True)),
                InlineKeyboardButton("Falso", callback_data=_answer_callback_data(number, False)),
            ]
        ]
    )


def _answer_result_keyboard(
    number: str, answer: bool, *, explanation_status: ExplanationStatus
) -> InlineKeyboardMarkup:
    """Offers "Spiega" alongside "Prossima domanda", unless there is nothing to explain.

    spec 0017, FR-2: `UNAVAILABLE` means a tap would always fail, so the button is
    not offered at all rather than offered and then shown failing.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if explanation_status is not ExplanationStatus.UNAVAILABLE:
        rows.append(
            [InlineKeyboardButton("Spiega", callback_data=_explain_callback_data(number, answer))]
        )
    rows.append([InlineKeyboardButton("Prossima domanda ▶", callback_data=NEXT_CALLBACK_DATA)])
    return InlineKeyboardMarkup(rows)


def _explanation_result_keyboard(number: str, *, translatable: bool) -> InlineKeyboardMarkup:
    """Offers "🇷🇺 Traduci" alongside "Prossima domanda", when there is text to translate.

    spec 0018 bot UX: `translatable` is only true for an `EXPLAINED` explanation
    with non-empty text, mirroring `_answer_result_keyboard`'s own omission rule
    for "Spiega" — a button that would always fail is not offered at all. Also
    reused, still with `translatable=True`, to restore the button after a failed
    translation attempt so the user can retry (`handle_translate_callback`).
    """
    rows: list[list[InlineKeyboardButton]] = []
    if translatable:
        rows.append(
            [InlineKeyboardButton("🇷🇺 Traduci", callback_data=_translate_callback_data(number))]
        )
    rows.append([InlineKeyboardButton("Prossima domanda ▶", callback_data=NEXT_CALLBACK_DATA)])
    return InlineKeyboardMarkup(rows)


async def _send_question(
    chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Proposes the next question in the chat's permutation and sends it (FR-1, FR-4)."""
    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    session: QuizSession | None = context.user_data.get("session")
    question, session = await service.propose_question(session, telegram_user_id)
    context.user_data["session"] = session

    keyboard = _question_keyboard(question.number)
    if question.image_url is None:
        await context.bot.send_message(chat_id=chat_id, text=question.text, reply_markup=keyboard)
        return

    image_bytes = await service.download_image(question.image_url, telegram_user_id)
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=BytesIO(image_bytes),
        caption=question.text,
        reply_markup=keyboard,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles `/start`: reports registration status, never proposes a question (FR-7)."""
    assert update.effective_chat is not None
    assert update.effective_user is not None
    service = container.resolve(context, QuizFlowService)
    registered = await service.check_registration_status(update.effective_user.id)
    text = messages.WELCOME_MESSAGE if registered else messages.PENDING_APPROVAL_MESSAGE
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles `/quiz`: proposes a question, resuming a pending session if any (FR-8)."""
    assert update.effective_chat is not None
    assert update.effective_user is not None
    await _send_question(update.effective_chat.id, update.effective_user.id, context)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ends the active session and shows its summary (spec 0016, FR-9).

    A failed summary call (network error, backend down) is **not** caught here: it
    propagates to the bot's single global error boundary (`handlers/error_handler.py`,
    spec 0015 FR-5) exactly like any other `QuizApiError`, and — critically — the
    session is not cleared in that case, since the `del` below is never reached
    (D-16).
    """
    assert update.effective_chat is not None
    assert update.effective_user is not None
    assert context.user_data is not None
    session: QuizSession | None = context.user_data.get("session")
    if session is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=messages.NO_SESSION_MESSAGE
        )
        return

    service = container.resolve(context, QuizFlowService)
    summary = await service.session_summary(update.effective_user.id, session.seed)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=messages.summary_message(summary.answered, summary.correct),
    )
    del context.user_data["session"]


async def handle_next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles "Prossima domanda ▶": proposes the next question (FR-4)."""
    assert update.callback_query is not None
    assert update.effective_chat is not None
    assert update.effective_user is not None
    await update.callback_query.answer()
    await _send_question(update.effective_chat.id, update.effective_user.id, context)


def _parse_callback(data: str, prefix: str) -> tuple[str, bool]:
    """Splits `{prefix}{number}:{0|1}` into the question number and the boolean flag."""
    rest = data.removeprefix(prefix)
    number, _, flag = rest.rpartition(":")
    return number, flag == "1"


async def handle_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Grades a tapped answer and offers to explain it (FR-2, FR-3; spec 0017 FR-1, FR-2)."""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    number, answer = _parse_callback(query.data, ANSWER_CALLBACK_PREFIX)

    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    session: QuizSession | None = context.user_data.get("session")
    try:
        correct, explanation_status = await service.handle_answer(
            session, number, answer, update.effective_user.id
        )
    except StaleQuestionError:
        await query.answer(messages.STALE_NOTICE)
        return

    await query.answer()
    text = messages.outcome_line(correct)
    keyboard = _answer_result_keyboard(number, answer, explanation_status=explanation_status)

    message = cast(Message, query.message)
    if message.photo:
        await query.edit_message_caption(caption=text, reply_markup=keyboard)
    else:
        await query.edit_message_text(text=text, reply_markup=keyboard)


async def handle_explain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ensures the labeling, fetches the explanation, and appends it in place (spec 0017 FR-3).

    Edits the message twice: an optimistic edit first (loading line, "Spiega"
    removed from the keyboard — AD-13, prevents a double-tap), then a final edit
    once `label` and `explanation` have both completed, in sequence. The final
    keyboard offers "🇷🇺 Traduci" only when there is text worth translating (spec
    0018 bot UX), and — in that same case — the shown Italian text is stashed on
    the session as `last_explanation`, so a later "Traduci" tap has something to
    send without re-parsing the message.
    """
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    number, answer = _parse_callback(query.data, EXPLAIN_CALLBACK_PREFIX)

    assert context.user_data is not None
    session: QuizSession | None = context.user_data.get("session")
    if session is None or session.current_question_number != number:
        await query.answer(messages.STALE_NOTICE)
        return

    await query.answer()
    message = cast(Message, query.message)
    base_text = message.caption if message.photo else message.text
    loading_text = f"{base_text}\n\n{messages.LOADING_EXPLANATION_LINE}"
    if message.photo:
        await query.edit_message_caption(caption=loading_text, reply_markup=_NEXT_KEYBOARD)
    else:
        await query.edit_message_text(text=loading_text, reply_markup=_NEXT_KEYBOARD)

    service = container.resolve(context, QuizFlowService)
    explanation = await service.handle_explanation_request(
        number, update.effective_user.id, answer
    )

    explanation_line = (
        messages.NO_EXPLANATION_LINE
        if explanation.status is ExplanationOutcome.INSUFFICIENT_KNOWLEDGE
        else (explanation.explanation or "")
    )
    translatable = explanation.status is ExplanationOutcome.EXPLAINED and bool(
        explanation.explanation
    )
    final_text = f"{base_text}\n\n{explanation_line}"
    final_keyboard = _explanation_result_keyboard(number, translatable=translatable)
    if message.photo:
        await query.edit_message_caption(caption=final_text, reply_markup=final_keyboard)
    else:
        await query.edit_message_text(text=final_text, reply_markup=final_keyboard)

    if translatable:
        assert explanation.explanation is not None
        context.user_data["session"] = session.model_copy(
            update={"last_explanation": explanation.explanation}
        )


async def handle_translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translates the shown explanation to Russian in place (spec 0018 bot UX).

    A callback query can be answered exactly once, and that answer must happen
    before the (possibly slow, up to the server's own translation deadline)
    translation call — otherwise Telegram's ~15s answer window can expire while
    waiting, exactly the reasoning `handle_explain_callback` already applies to
    `label`+`explanation`. That spends the one native "alert" channel early, so a
    translation failure cannot show as a popup: it reverts the optimistic edit
    back to its pre-tap state (button restored, so the user can retry) and reports
    the failure as a short follow-up chat message instead.

    A photo message's caption is never extended with the translation (Telegram's
    1024-char caption limit): on success the caption reverts to its pre-tap text
    and the Russian text is sent as a separate message in the same chat.
    """
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_chat is not None
    assert update.effective_user is not None
    number = query.data.removeprefix(TRANSLATE_CALLBACK_PREFIX)

    assert context.user_data is not None
    session: QuizSession | None = context.user_data.get("session")
    if (
        session is None
        or session.current_question_number != number
        or session.last_explanation is None
    ):
        await query.answer(messages.STALE_NOTICE)
        return

    await query.answer()
    message = cast(Message, query.message)
    pre_text = message.caption if message.photo else message.text
    loading_text = f"{pre_text}\n\n{messages.LOADING_TRANSLATION_LINE}"
    if message.photo:
        await query.edit_message_caption(caption=loading_text, reply_markup=_NEXT_KEYBOARD)
    else:
        await query.edit_message_text(text=loading_text, reply_markup=_NEXT_KEYBOARD)

    service = container.resolve(context, QuizFlowService)
    try:
        translated = await service.handle_translation_request(
            session.last_explanation, update.effective_user.id
        )
    except QuizApiError:
        retry_keyboard = _explanation_result_keyboard(number, translatable=True)
        if message.photo:
            await query.edit_message_caption(caption=pre_text, reply_markup=retry_keyboard)
        else:
            await query.edit_message_text(text=cast(str, pre_text), reply_markup=retry_keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=messages.TRANSLATION_ERROR_MESSAGE
        )
        return

    translated_line = f"🇷🇺 {translated}"
    if message.photo:
        await query.edit_message_caption(caption=pre_text, reply_markup=_NEXT_KEYBOARD)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=translated_line)
    else:
        final_text = f"{pre_text}\n\n{translated_line}"
        await query.edit_message_text(text=final_text, reply_markup=_NEXT_KEYBOARD)
