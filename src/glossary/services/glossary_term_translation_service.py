from collections.abc import Sequence

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.agents.glossary_term_translator.dto import (
    GlossaryTermTranslatorRequest,
    TermToTranslateDto,
)
from glossary.agents.glossary_term_translator.glossary_term_translator_agent import (
    GlossaryTermTranslatorAgent,
)
from glossary.models import GlossaryTermRow, TranslatedTerm


@service
class GlossaryTermTranslationService(
    AsyncUseCase[Sequence[GlossaryTermRow], list[TranslatedTerm]]
):
    """Runs the term translator agent over one batch. Never touches the database."""

    agent: Autowired[GlossaryTermTranslatorAgent]

    async def execute(self, request: Sequence[GlossaryTermRow]) -> list[TranslatedTerm]:
        response = await self.agent.run(
            GlossaryTermTranslatorRequest(
                entries=[
                    TermToTranslateDto(term=row.term, definition=row.definition) for row in request
                ]
            )
        )
        return [
            TranslatedTerm(term=row.term, term_ru=item.term_ru)
            for row, item in zip(request, response.translations, strict=True)
        ]
