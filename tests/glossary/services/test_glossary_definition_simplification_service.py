from glossary.services.glossary_definition_simplification_service import (
    GlossaryDefinitionSimplificationService,
)

from glossary.agents.glossary_definition_simplifier.dto import (
    GlossaryDefinitionSimplifierResponse,
    SimplifiedDefinitionItemDto,
)
from glossary.models import GlossaryDefinitionRow


class _FakeAgent:
    def __init__(self, response: GlossaryDefinitionSimplifierResponse) -> None:
        self._response = response
        self.calls = 0

    async def run(self, request):  # noqa: ANN001, ANN201
        self.calls += 1
        return self._response


def _service(agent: _FakeAgent) -> GlossaryDefinitionSimplificationService:
    service = GlossaryDefinitionSimplificationService.__new__(
        GlossaryDefinitionSimplificationService
    )
    service.agent = agent  # type: ignore[attr-defined]
    return service


async def test_it_simplifies_a_batch_aligned_by_position() -> None:
    rows = [
        GlossaryDefinitionRow(id=1, term="carreggiata", definition="def1"),
        GlossaryDefinitionRow(id=2, term="banchina", definition="def2"),
    ]
    agent = _FakeAgent(
        GlossaryDefinitionSimplifierResponse(
            simplifications=[
                SimplifiedDefinitionItemDto(definition_plain="La strada per i veicoli."),
                SimplifiedDefinitionItemDto(
                    definition_plain="Il lato della strada non asfaltato."
                ),
            ]
        )
    )

    result = await _service(agent)(rows)

    from glossary.models import SimplifiedDefinition

    assert result == [
        SimplifiedDefinition(term="carreggiata", definition_plain="La strada per i veicoli."),
        SimplifiedDefinition(
            term="banchina", definition_plain="Il lato della strada non asfaltato."
        ),
    ]
    assert agent.calls == 1
