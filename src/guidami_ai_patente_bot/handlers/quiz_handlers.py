"""Telegram update handlers: thin controllers over QuizFlowService (AD-5, spec 0016 AD-11)."""

from io import BytesIO
from typing import cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from guidami_ai_patente_bot import container, messages
from guidami_ai_patente_bot.configs import BotConfig
from guidami_ai_patente_bot.enums import ExplanationOutcome, ExplanationStatus, SessionMode
from guidami_ai_patente_bot.exceptions import (
    QuizApiError,
    SessionCompletedError,
    StaleQuestionError,
)
from guidami_ai_patente_bot.models import CitedGlossaryTerm, QuizQuestion, QuizSession
from guidami_ai_patente_bot.services import QuizFlowService

ANSWER_CALLBACK_PREFIX = "quiz:answer:"
EXPLAIN_CALLBACK_PREFIX = "quiz:explain:"
TRANSLATE_CALLBACK_PREFIX = "quiz:translate:"
NEXT_CALLBACK_DATA = "quiz:next"

# Telegram's cap on a photo's caption. A question's own caption sits far below it, so only
# the explanation appended to it can overflow (see `handle_explain_callback`).
_CAPTION_LIMIT = 1024

# Telegram's cap on a plain text message (the non-photo counterpart of `_CAPTION_LIMIT`).
# `term_explanation` (up to ~900 chars) plus the legal explanation plus a multi-line
# glossary block can realistically exceed this once combined with the question text.
_TEXT_LIMIT = 4096

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


def _glossary_block(hints: tuple[CitedGlossaryTerm, ...]) -> str:
    """Renders FR-8's glossary block: one '📖 term — definition' line per hint."""
    return "\n".join(f"📖 {hint.term} — {hint.definition}" for hint in hints)


def _chunk_text(text: str, limit: int = _TEXT_LIMIT) -> list[str]:
    """Splits `text` into chunks of at most `limit` chars, none dropped.

    Greedily packs whole blank-line-separated sections into a chunk, so a section (e.g.
    the vocabulary paragraph, the legal explanation, one glossary line) stays intact
    whenever it fits. A single section still longer than `limit` on its own is
    hard-split at the character limit as a last resort — content is only ever split
    further, never dropped.
    """
    sections = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n\n{section}" if current else section
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
                current = ""
            if len(section) <= limit:
                current = section
            else:
                chunks.extend(
                    section[start : start + limit] for start in range(0, len(section), limit)
                )
    if current:
        chunks.append(current)
    return chunks


async def _send_text(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends `text` as one or more `send_message` calls, none exceeding `_TEXT_LIMIT`."""
    for chunk in _chunk_text(text):
        await context.bot.send_message(chat_id=chat_id, text=chunk)


async def _deliver_question(
    chat_id: int,
    telegram_user_id: int,
    question: QuizQuestion,
    service: QuizFlowService,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Sends `question` with its Vero/Falso keyboard, as a photo when it has an image."""
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


async def _finish_session(
    chat_id: int,
    telegram_user_id: int,
    session: QuizSession,
    service: QuizFlowService,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Sends the session summary and clears the session (shared by /stop and completion).

    A failed summary call is not caught: the session is then left in place (D-16).
    """
    assert context.user_data is not None
    summary = await service.session_summary(telegram_user_id, session.seed)
    await context.bot.send_message(chat_id=chat_id, text=messages.summary_message(summary))
    del context.user_data["session"]


async def _send_question(
    chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Proposes the next question for the chat's session and sends it (FR-1, FR-4).

    When a TOPIC or REVIEW session has no more questions, announces the completion,
    shows the same summary as `/stop` and clears the session (spec FR-7).
    """
    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    session: QuizSession | None = context.user_data.get("session")
    try:
        question, session = await service.propose_question(session, telegram_user_id)
    except SessionCompletedError:
        assert session is not None
        text = (
            messages.REVIEW_COMPLETED_MESSAGE
            if session.mode is SessionMode.REVIEW
            else messages.TOPIC_COMPLETED_MESSAGE
        )
        await context.bot.send_message(chat_id=chat_id, text=text)
        await _finish_session(chat_id, telegram_user_id, session, service, context)
        return
    context.user_data["session"] = session
    await _deliver_question(chat_id, telegram_user_id, question, service, context)


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
    assert context.user_data is not None
    if "session" not in context.user_data:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=messages.QUIZ_INTRO_MESSAGE
        )
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
    await _finish_session(
        update.effective_chat.id, update.effective_user.id, session, service, context
    )


async def statistiche_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles `/statistiche`: shows the user's mastery statistics (FR-6)."""
    assert update.effective_chat is not None
    assert update.effective_user is not None
    service = container.resolve(context, QuizFlowService)
    config = container.resolve(context, BotConfig)
    stats = await service.get_statistics(update.effective_user.id)
    text = messages.statistics_message(stats, config.topic_label_max_chars)
    await _send_text(update.effective_chat.id, text, context)


async def ripasso_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles `/ripasso`: starts a review session, replacing any in progress (FR-7).

    With nothing to review, replies so and clears any existing session, so no
    session remains (the success path likewise replaces without a summary).
    """
    assert update.effective_chat is not None
    assert update.effective_user is not None
    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        question, session = await service.start_session(SessionMode.REVIEW, None, user_id)
    except SessionCompletedError:
        context.user_data.pop("session", None)
        await context.bot.send_message(chat_id=chat_id, text=messages.NO_REVIEW_MESSAGE)
        return
    context.user_data["session"] = session
    await _deliver_question(chat_id, user_id, question, service, context)


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
    message = cast(Message, query.message)
    question_text = message.caption if message.photo else message.text
    text = f"{question_text}\n\n{messages.outcome_line(correct)}"
    keyboard = _answer_result_keyboard(number, answer, explanation_status=explanation_status)

    if message.photo:
        await query.edit_message_caption(caption=text, reply_markup=keyboard)
    else:
        await query.edit_message_text(text=text, reply_markup=keyboard)


async def handle_explain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ensures the labeling, fetches the explanation, and appends it in place (spec 0017 FR-3).

    Edits the message twice: an optimistic edit first (loading line, "Spiega"
    removed from the keyboard — AD-13, prevents a double-tap), then a final edit
    once `label` and `explanation` have both completed, in sequence. The final
    body renders up to three sections, in order (spec 0020 FR-7, FR-8):
    `term_explanation` (vocabulary prose), the legal explanation line, and the
    `_glossary_block` built from `translation_hints` — any section that is empty
    is simply omitted, never rendered as a blank line. The final keyboard offers
    "🇷🇺 Traduci" whenever there is text worth translating (spec 0018 bot UX): either
    the legal stage succeeded, or — AD-1, the two stages are independent —
    `term_explanation` is a real, non-null sentence even though the legal stage
    itself refused. In that same case, the full rendered body (not just the legal
    explanation) is stashed on the session as `last_explanation`, together with
    `last_explanation_hints`, so a later "Traduci" tap translates everything the
    user was shown, and can forward the same hints (FR-7's "what you see is what
    you translate" guarantee). A text (non-photo) message that would exceed
    Telegram's 4096-char limit is edited down to just the question text, with the
    full body sent as one or more separate follow-up messages (`_send_text`),
    mirroring the photo path's existing `_CAPTION_LIMIT` overflow guard. The
    follow-up body itself is never dropped or hard-capped: `_send_text` chunks it
    across multiple `send_message` calls whenever it alone exceeds 4096 chars —
    realistic once `term_explanation` and a multi-line glossary block are both
    present.
    """
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_chat is not None
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
    sections = [
        section
        for section in (
            explanation.term_explanation,
            explanation_line,
            _glossary_block(explanation.translation_hints),
        )
        if section
    ]
    body = "\n\n".join(sections)
    # AD-1: the legal and vocabulary stages are independent, so a refused legal
    # explanation (INSUFFICIENT_KNOWLEDGE) still has something worth translating
    # whenever the vocabulary stage produced a real term_explanation.
    translatable = (
        explanation.status is ExplanationOutcome.EXPLAINED and bool(explanation.explanation)
    ) or bool(explanation.term_explanation)
    final_text = f"{base_text}\n\n{body}"
    final_keyboard = _explanation_result_keyboard(number, translatable=translatable)
    if message.photo and len(final_text) > _CAPTION_LIMIT:
        await query.edit_message_caption(caption=base_text, reply_markup=final_keyboard)
        await _send_text(update.effective_chat.id, body, context)
    elif message.photo:
        await query.edit_message_caption(caption=final_text, reply_markup=final_keyboard)
    elif len(final_text) > _TEXT_LIMIT:
        await query.edit_message_text(text=cast(str, base_text), reply_markup=final_keyboard)
        await _send_text(update.effective_chat.id, body, context)
    else:
        await query.edit_message_text(text=final_text, reply_markup=final_keyboard)

    if translatable:
        context.user_data["session"] = session.model_copy(
            update={
                "last_explanation": body,
                "last_explanation_hints": explanation.translation_hints,
            }
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
    and the Russian text is sent as a separate message in the same chat. A text
    (non-photo) message follows the same rule once appending the translation would
    exceed Telegram's 4096-char text limit — `pre_text` alone can already sit close
    to that limit, and the translation roughly doubles the body — reverting the
    message to `pre_text` and sending the translation as a separate follow-up
    message instead, mirroring `handle_explain_callback`'s own text-overflow guard.
    Every follow-up translation message goes through `_send_text`, so a translation
    long enough to exceed 4096 chars on its own is chunked across several
    `send_message` calls rather than dropped.

    `pre_text` itself is not bounded by this handler — it is whatever the pre-tap
    message already held, which spec 0020's `handle_explain_callback` guarantees
    stays within Telegram's 4096-char limit — but the *loading* edit appends
    `LOADING_TRANSLATION_LINE` on top of it, which can push a `pre_text` sitting
    close to that limit over it. That combined edit is size-checked the same way:
    when it would overflow, the loading line is dropped and the edit carries
    `pre_text` alone (still swapping in `_NEXT_KEYBOARD` to disable the button and
    prevent a double-tap, AD-13) — the loading indicator is decorative, so it is the
    one piece of content this handler is allowed to simply omit rather than split.
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
    elif len(loading_text) <= _TEXT_LIMIT:
        await query.edit_message_text(text=loading_text, reply_markup=_NEXT_KEYBOARD)
    else:
        await query.edit_message_text(text=cast(str, pre_text), reply_markup=_NEXT_KEYBOARD)

    service = container.resolve(context, QuizFlowService)
    try:
        translated = await service.handle_translation_request(
            session.last_explanation, update.effective_user.id, session.last_explanation_hints
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
        await _send_text(update.effective_chat.id, translated_line, context)
        return

    final_text = f"{pre_text}\n\n{translated_line}"
    if len(final_text) > _TEXT_LIMIT:
        await query.edit_message_text(text=cast(str, pre_text), reply_markup=_NEXT_KEYBOARD)
        await _send_text(update.effective_chat.id, translated_line, context)
    else:
        await query.edit_message_text(text=final_text, reply_markup=_NEXT_KEYBOARD)
