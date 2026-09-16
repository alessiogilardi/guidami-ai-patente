"""Entry point: loads configuration and runs the bot's whole async lifecycle."""

import asyncio
import contextlib
import logging
import signal

from pywire import get_default_container
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .clients import QuizApiClient  # noqa: F401  — imported for pywire registration
from .configs import BotConfig
from .handlers.error_handler import handle_error
from .handlers.quiz_handlers import (
    ANSWER_CALLBACK_PREFIX,
    NEXT_CALLBACK_DATA,
    handle_answer_callback,
    handle_next_callback,
    start_or_quiz,
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Boots the Telegram bot process."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


async def _run() -> None:
    """Runs pywire's async beans, then `python-telegram-bot`'s own, in one scope.

    `container.lifespan()` enters every `@async_component` (here, `QuizApiClient`)
    on the way in and exits it on the way out (pywire 0.9.0) — the module import
    above is what makes `QuizApiClient` visible to `astart()` before it runs, per
    pywire's "import every module declaring an `@async_component` before starting
    the container" rule.
    """
    config = BotConfig()  # pyright: ignore[reportCallIssue]
    get_default_container().register_instance(config, as_type=BotConfig)

    application = Application.builder().token(config.telegram_bot_token.get_secret_value()).build()
    assert application.updater is not None
    application.add_handler(CommandHandler(["start", "quiz"], start_or_quiz))
    application.add_handler(
        CallbackQueryHandler(handle_answer_callback, pattern=f"^{ANSWER_CALLBACK_PREFIX}")
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
        await stop_event.wait()
        await application.updater.stop()
        await application.stop()


if __name__ == "__main__":
    main()
