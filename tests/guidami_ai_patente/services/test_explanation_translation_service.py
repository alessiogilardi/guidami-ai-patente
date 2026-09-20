"""spec 0018: translate `text` via ExplanationTranslatorAgent, or fail as a 503."""

import asyncio
from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.agents.explanation_translator.dto import (
    ExplanationTranslatorRequest,
    ExplanationTranslatorResponse,
)
from guidami_ai_patente.exceptions import ExplanationUnavailableError
from guidami_ai_patente.services import ExplanationTranslationService


@dataclass
class _TranslatorDouble:
    responses: list[ExplanationTranslatorResponse] = field(default_factory=list)
    error: Exception | None = None
    requests: list[ExplanationTranslatorRequest] = field(default_factory=list)

    async def run(self, request: ExplanationTranslatorRequest) -> ExplanationTranslatorResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


@dataclass
class _ConfigDouble:
    translation_deadline_s: float = 5.0


def _service(translator: _TranslatorDouble) -> ExplanationTranslationService:
    service = object.__new__(ExplanationTranslationService)
    service.config = _ConfigDouble()  # type: ignore[assignment]
    service.translator = translator  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_the_translated_text_is_returned() -> None:
    translator = _TranslatorDouble(
        responses=[ExplanationTranslatorResponse(translated_text="Перевод.")]
    )

    result = await _service(translator)("Testo da tradurre.")

    assert result == "Перевод."
    assert translator.requests[0].text == "Testo da tradurre."


@pytest.mark.asyncio
async def test_an_agent_failure_becomes_a_503() -> None:
    translator = _TranslatorDouble(error=RuntimeError("provider is down"))

    with pytest.raises(ExplanationUnavailableError):
        await _service(translator)("Testo da tradurre.")


@pytest.mark.asyncio
async def test_exceeding_the_deadline_becomes_a_503() -> None:
    """A timeout is an outage, never a statement about the translation itself."""

    @dataclass
    class _SlowTranslator:
        requests: list[ExplanationTranslatorRequest] = field(default_factory=list)

        async def run(
            self, request: ExplanationTranslatorRequest
        ) -> ExplanationTranslatorResponse:
            self.requests.append(request)
            await asyncio.sleep(1)
            return ExplanationTranslatorResponse(translated_text="Перевод.")

    service = _service(_SlowTranslator())  # type: ignore[arg-type]
    service.config = _ConfigDouble(translation_deadline_s=0.01)  # type: ignore[assignment]

    with pytest.raises(ExplanationUnavailableError):
        await service("Testo da tradurre.")
