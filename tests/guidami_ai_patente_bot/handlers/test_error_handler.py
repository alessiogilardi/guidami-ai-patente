"""The global error boundary logs once and notifies the chat if one exists (FR-5)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, Update

from guidami_ai_patente_bot.handlers.error_handler import handle_error
from guidami_ai_patente_bot.messages import GENERIC_ERROR_MESSAGE


def _update_with_chat(chat_id: int) -> Update:
    chat = Chat(id=chat_id, type=Chat.PRIVATE)
    message = Message(message_id=1, date=datetime.now(UTC), chat=chat)
    return Update(update_id=1, message=message)


@pytest.mark.asyncio
async def test_a_failure_with_an_identifiable_chat_sends_the_generic_message() -> None:
    context = SimpleNamespace(bot=AsyncMock(), error=RuntimeError("boom"))
    update = _update_with_chat(42)

    await handle_error(update, context)

    context.bot.send_message.assert_awaited_once_with(chat_id=42, text=GENERIC_ERROR_MESSAGE)


@pytest.mark.asyncio
async def test_a_non_update_object_is_logged_without_sending_anything() -> None:
    context = SimpleNamespace(bot=AsyncMock(), error=RuntimeError("boom"))

    await handle_error(None, context)

    context.bot.send_message.assert_not_awaited()
