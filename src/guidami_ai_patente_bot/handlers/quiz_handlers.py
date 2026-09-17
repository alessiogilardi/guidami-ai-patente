"""Telegram update handlers: thin controllers over QuizFlowService (AD-5)."""

from io import BytesIO
from typing import cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from guidami_ai_patente_bot import container, messages
from guidami_ai_patente_bot.enums import ExplanationOutcome
from guidami_ai_patente_bot.exceptions import StaleQuestionError
from guidami_ai_patente_bot.models import QuizSession
from guidami_ai_patente_bot.services import QuizFlowService

ANSWER_CALLBACK_PREFIX = "quiz:answer:"
NEXT_CALLBACK_DATA = "quiz:next"

_NEXT_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Prossima domanda ▶", callback_data=NEXT_CALLBACK_DATA)]]
)


def _answer_callback_data(number: str, answer: bool) -> str:
    return f"{ANSWER_CALLBACK_PREFIX}{number}:{int(answer)}"


def _question_keyboard(number: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Vero", callback_data=_answer_callback_data(number, True)),
                InlineKeyboardButton("Falso", callback_data=_answer_callback_data(number, False)),
            ]
        ]
    )


async def _send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Proposes the next question in the chat's permutation and sends it (FR-1, FR-4).

    Always sends a *new* message — see the plan's design note on why "Prossima
    domanda" does not edit the previous one.
    """
    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    session: QuizSession | None = context.user_data.get("session")
    question, session = await service.propose_question(session)
    context.user_data["session"] = session

    keyboard = _question_keyboard(question.number)
    if question.image_url is None:
        await context.bot.send_message(chat_id=chat_id, text=question.text, reply_markup=keyboard)
        return

    image_bytes = await service.download_image(question.image_url)
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=BytesIO(image_bytes),
        caption=question.text,
        reply_markup=keyboard,
    )


async def start_or_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles `/start` and `/quiz`: proposes a question (FR-1)."""
    assert update.effective_chat is not None
    await _send_question(update.effective_chat.id, context)


async def handle_next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles "Prossima domanda ▶": proposes the next question (FR-4)."""
    assert update.callback_query is not None
    assert update.effective_chat is not None
    await update.callback_query.answer()
    await _send_question(update.effective_chat.id, context)


async def handle_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Grades a tapped answer and shows its explanation in the same turn (FR-2, FR-3)."""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    rest = query.data.removeprefix(ANSWER_CALLBACK_PREFIX)
    number, _, flag = rest.rpartition(":")
    answer = flag == "1"

    assert context.user_data is not None
    service = container.resolve(context, QuizFlowService)
    session: QuizSession | None = context.user_data.get("session")
    try:
        correct, explanation = await service.handle_answer(session, number, answer)
    except StaleQuestionError:
        await query.answer(messages.STALE_NOTICE)
        return

    await query.answer()
    outcome_line = messages.outcome_line(correct)
    explanation_line = (
        messages.NO_EXPLANATION_LINE
        if explanation.status is ExplanationOutcome.INSUFFICIENT_KNOWLEDGE
        else (explanation.explanation or "")
    )
    text = f"{outcome_line}\n\n{explanation_line}"

    message = cast(Message, query.message)
    if message.photo:
        await query.edit_message_caption(caption=text, reply_markup=_NEXT_KEYBOARD)
    else:
        await query.edit_message_text(text=text, reply_markup=_NEXT_KEYBOARD)
