import pytest
from glossary.agents.glossary_definition_simplifier.glossary_definition_simplifier_agent import (
    GlossaryDefinitionSimplifierAgent,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import NullLlmCallTracker
from glossary.agents.glossary_definition_simplifier.dto import (
    DefinitionToSimplifyDto,
    GlossaryDefinitionSimplifierRequest,
)

_PROVIDER = OpenRouterProvider(api_key="test-key")
_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Definizioni: $entries_block",
    num_retries=3,
)


def _agent() -> GlossaryDefinitionSimplifierAgent:
    """Passes `tracker` explicitly too — see `GlossaryExtractorAgent`'s test for why."""
    return GlossaryDefinitionSimplifierAgent(_TEST_CONFIG, _PROVIDER, NullLlmCallTracker())


def _scripted_model(simplification_lists: list[list[dict]]) -> FunctionModel:
    calls = {"n": 0}

    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        tool_name = info.output_tools[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name, {"simplifications": simplification_lists[calls["n"] - 1]})
            ]
        )

    return FunctionModel(_func)


async def test_a_count_mismatch_self_corrects_on_retry() -> None:
    agent = _agent()
    request = GlossaryDefinitionSimplifierRequest(
        entries=[DefinitionToSimplifyDto(term="carreggiata", definition="def")]
    )
    too_few: list[dict] = []
    correct = [{"definition_plain": "La parte della strada per i veicoli."}]

    with agent.core_agent.override(model=_scripted_model([too_few, correct])):
        response = await agent.run(request)

    assert response.simplifications[0].definition_plain == "La parte della strada per i veicoli."


async def test_a_persistent_count_mismatch_exhausts_retries() -> None:
    agent = _agent()
    request = GlossaryDefinitionSimplifierRequest(
        entries=[DefinitionToSimplifyDto(term="carreggiata", definition="def")]
    )
    too_many = [
        {"definition_plain": "a"},
        {"definition_plain": "b"},
    ]

    with (
        agent.core_agent.override(model=_scripted_model([too_many, too_many, too_many, too_many])),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await agent.run(request)
