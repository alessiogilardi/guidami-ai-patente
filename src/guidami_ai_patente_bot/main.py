"""Entry point: loads configuration and runs the bot's whole async lifecycle."""

import asyncio
import contextlib
import logging
import signal

from pywire import get_default_container
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from . import container
from .clients import QuizApiClient
from .configs import BotConfig
from .handlers.error_handler import handle_error
from .handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    EXPLAIN_CALLBACK_PREFIX,
    NEXT_CALLBACK_DATA,
    handle_answer_callback,
    handle_explain_callback,
    handle_next_callback,
    quiz_command,
    start_command,
    stop_command,
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Boots the Telegram bot process."""
    logging.basicConfig(level=logging.INFO)
    # httpx logs each request at INFO with the full URL, and Telegram's Bot API URL
    # embeds the bot token unmasked (https://api.telegram.org/bot<TOKEN>/getUpdates) —
    # silence it to WARNING so the token never hits stdout on every long-poll request.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(_run())


async def _run() -> None:
    """Runs pywire's async beans, then `python-telegram-bot`'s own, in one scope.

    `container.lifespan()` enters every registered async component (here,
    `QuizApiClient`) on the way in and exits it on the way out (pywire 0.9.0).
    `QuizApiClient` is registered explicitly below via `register_async_component`,
    rather than via the `@async_component` class decorator, precisely so importing
    the `clients` package has no side effect on the shared default container that
    `guidami_ai_patente`'s FastAPI app also uses (see `QuizApiClient`'s docstring).
    """
    config = BotConfig()  # pyright: ignore[reportCallIssue]
    get_default_container().register_instance(config, as_type=BotConfig)
    get_default_container().register_async_component(QuizApiClient)

    application = (
        Application.builder()
        .token(config.telegram_bot_token.get_secret_value())
        .read_timeout(config.telegram_read_timeout_seconds)
        .build()
    )
    application.bot_data[container.BOT_DATA_CONTAINER_KEY] = get_default_container()
    assert application.updater is not None
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(
        CallbackQueryHandler(handle_answer_callback, pattern=f"^{ANSWER_CALLBACK_PREFIX}")
    )
    application.add_handler(
        CallbackQueryHandler(handle_explain_callback, pattern=f"^{EXPLAIN_CALLBACK_PREFIX}")
    )
    application.add_handler(
        CallbackQueryHandler(handle_next_callback, pattern=f"^{NEXT_CALLBACK_DATA}$")
    )
    application.add_error_handler(handle_error)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows has no add_signal_handler; Ctrl+C surfaces as a plain
        # KeyboardInterrupt instead, which unwinds the `async with` blocks below the
        # same way — container.lifespan() and application's own __aexit__ both run
        # their teardown in a finally regardless of how the body exits.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    logger.info("Starting Telegram bot against %s", config.api_base_url)
    async with get_default_container().lifespan(), application:
        await application.start()
        await application.updater.start_polling()
        try:
            await stop_event.wait()
        finally:
            await application.updater.stop()
            await application.stop()


if __name__ == "__main__":
    main()
