"""Translates an already-produced Italian explanation to Russian (spec 0018)."""

import asyncio
import logging

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from guidami_ai_patente.agents import ExplanationTranslatorAgent
from guidami_ai_patente.agents.explanation_translator.dto import ExplanationTranslatorRequest
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.exceptions import ExplanationUnavailableError

logger = logging.getLogger(__name__)


@service
class ExplanationTranslationService(AsyncUseCase[str, str]):
    """Translates `text` to Russian via `ExplanationTranslatorAgent` (spec 0018, FR-1, FR-7).

    Takes and returns a plain `str` rather than a one-field wrapper DTO: the service
    reduces to exactly one input and one output, and
    `.claude/rules/use-case-invocation.md` only asks for a request DTO once a method
    needs more than one scalar argument (mirrors `CurrentLabelingReadService`'s own
    `AsyncUseCase[str, CommaSelection]`).

    Reuses `ExplanationUnavailableError` for both a timeout and an agent-call failure
    (spec 0018, AD-4): the meaning is identical to what `ExplanationService`/
    `LabelingService` already report with it — an LLM-backed stage of the explanation
    feature failed or timed out — so this raises the same exception rather than a new
    `TranslationUnavailableError`, already mapped to `503` by the existing handler.
    """

    config: Autowired[AppConfig]
    translator: Autowired[ExplanationTranslatorAgent]

    async def execute(self, text: str) -> str:
        """Translates `text` to Russian, or raises if the agent fails or times out.

        Args:
            text: The Italian text to translate.

        Raises:
            ExplanationUnavailableError: The agent failed, or the call exceeded its
                deadline (spec 0018, AD-4, AD-5).
        """
        try:
            async with asyncio.timeout(self.config.translation_deadline_s):
                response = await self.translator.run(ExplanationTranslatorRequest(text=text))
        except TimeoutError as error:
            logger.warning(
                "Translation exceeded its %.1fs budget", self.config.translation_deadline_s
            )
            raise ExplanationUnavailableError(
                f"the translation exceeded the {self.config.translation_deadline_s:.0f}s budget"
            ) from error
        except Exception as error:
            logger.warning("Translation agent failed", exc_info=True)
            raise ExplanationUnavailableError("the translation agent failed") from error
        return response.translated_text
