from collections.abc import Sequence

from pywire import Autowired, service

from commons.use_cases import AsyncUseCase
from glossary.agents.glossary_definition_simplifier.dto import (
    DefinitionToSimplifyDto,
    GlossaryDefinitionSimplifierRequest,
)
from glossary.agents.glossary_definition_simplifier.glossary_definition_simplifier_agent import (
    GlossaryDefinitionSimplifierAgent,
)
from glossary.models import GlossaryDefinitionRow, SimplifiedDefinition


@service
class GlossaryDefinitionSimplificationService(
    AsyncUseCase[Sequence[GlossaryDefinitionRow], list[SimplifiedDefinition]]
):
    """Runs the definition simplifier agent over one batch. Never touches the database."""

    agent: Autowired[GlossaryDefinitionSimplifierAgent]

    async def execute(
        self, request: Sequence[GlossaryDefinitionRow]
    ) -> list[SimplifiedDefinition]:
        """Simplifies one batch of rows, aligned 1:1 to `request` by position."""
        response = await self.agent.run(
            GlossaryDefinitionSimplifierRequest(
                entries=[
                    DefinitionToSimplifyDto(term=row.term, definition=row.definition)
                    for row in request
                ]
            )
        )
        return [
            SimplifiedDefinition(term=row.term, definition_plain=item.definition_plain)
            for row, item in zip(request, response.simplifications, strict=True)
        ]
