"""Global error boundary: logs once, notifies the chat if identified (FR-5, spec 0016 FR-10)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from guidami_ai_patente_bot import messages
from guidami_ai_patente_bot.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the failure once, at the single global boundary (FR-5), with a message per case."""
    logger.error("Unhandled error while processing an update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat is not None:
        text = (
            messages.UNAUTHORIZED_MESSAGE
            if isinstance(context.error, UnauthorizedError)
            else messages.GENERIC_ERROR_MESSAGE
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
