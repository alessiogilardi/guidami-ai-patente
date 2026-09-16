"""Global error boundary: logs once, notifies the chat if one can be identified (FR-5)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Si è verificato un errore, riprova con /quiz"


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the failure once, at the single global boundary (FR-5)."""
    logger.error("Unhandled error while processing an update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat is not None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=GENERIC_ERROR_MESSAGE
        )
