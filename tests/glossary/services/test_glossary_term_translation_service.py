from glossary.agents.glossary_term_translator.dto import (
    GlossaryTermTranslatorResponse,
    TranslatedTermItemDto,
)
from glossary.models import GlossaryTermRow
from glossary.services.glossary_term_translation_service import GlossaryTermTranslationService


class _FakeAgent:
    def __init__(self, response: GlossaryTermTranslatorResponse) -> None:
        self._response = response
        self.calls = 0

    async def run(self, request):  # noqa: ANN001, ANN201
        self.calls += 1
        return self._response


def _service(agent: _FakeAgent) -> GlossaryTermTranslationService:
    service = GlossaryTermTranslationService.__new__(GlossaryTermTranslationService)
    service.agent = agent  # type: ignore[attr-defined]
    return service


async def test_it_translates_a_batch_aligned_by_position() -> None:
    rows = [
        GlossaryTermRow(id=1, term="carreggiata", definition="def1"),
        GlossaryTermRow(id=2, term="banchina", definition="def2"),
    ]
    agent = _FakeAgent(
        GlossaryTermTranslatorResponse(
            translations=[
                TranslatedTermItemDto(term_ru="проезжая часть"),
                TranslatedTermItemDto(term_ru="обочина"),
            ]
        )
    )

    result = await _service(agent)(rows)

    assert result == [
        __import__("glossary.models", fromlist=["TranslatedTerm"]).TranslatedTerm(
            term="carreggiata", term_ru="проезжая часть"
        ),
        __import__("glossary.models", fromlist=["TranslatedTerm"]).TranslatedTerm(
            term="banchina", term_ru="обочина"
        ),
    ]
    assert agent.calls == 1
