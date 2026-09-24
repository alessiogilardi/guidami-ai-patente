import pytest
from glossary.agents.glossary_extractor.glossary_extractor_agent import GlossaryExtractorAgent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import NullLlmCallTracker
from glossary.agents.glossary_extractor.dto import GlossaryExtractorRequest

_PROVIDER = OpenRouterProvider(api_key="test-key")
_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Testo: $block_text",
    num_retries=3,
)
_BLOCK_TEXT = "1) ALFA: significato di alfa. 2) BETA: significato di beta."


def _agent() -> GlossaryExtractorAgent:
    """Passes `tracker` explicitly too — `GlossaryExtractorAgent.__init__` falls back to
    the autowired `self.tracker` otherwise, which raises `AttributeError` here since this
    bypasses the pywire container entirely (see the constructor's own docstring).
    """
    return GlossaryExtractorAgent(_TEST_CONFIG, _PROVIDER, NullLlmCallTracker())


def _scripted_model(entry_lists: list[list[dict]]) -> FunctionModel:
    calls = {"n": 0}

    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        tool_name = info.output_tools[0].name
        return ModelResponse(
            parts=[ToolCallPart(tool_name, {"entries": entry_lists[calls["n"] - 1]})]
        )

    return FunctionModel(_func)


async def test_a_non_verbatim_definition_self_corrects_on_retry() -> None:
    agent = _agent()
    request = GlossaryExtractorRequest(block_text=_BLOCK_TEXT)
    bad = [{"term": "ALFA", "definition": "un significato inventato"}]
    good = [{"term": "ALFA", "definition": "significato di alfa"}]

    with agent.core_agent.override(model=_scripted_model([bad, good])):
        response = await agent.run(request)

    assert response.entries[0].definition == "significato di alfa"


async def test_an_absent_term_never_self_corrects_and_exhausts_retries() -> None:
    agent = _agent()
    request = GlossaryExtractorRequest(block_text=_BLOCK_TEXT)
    bad = [{"term": "GAMMA inesistente", "definition": "significato di alfa"}]

    with (
        agent.core_agent.override(model=_scripted_model([bad, bad, bad, bad])),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await agent.run(request)


async def test_a_duplicate_term_is_rejected() -> None:
    agent = _agent()
    request = GlossaryExtractorRequest(block_text=_BLOCK_TEXT)
    duplicate = [
        {"term": "ALFA", "definition": "significato di alfa"},
        {"term": "ALFA", "definition": "significato di alfa"},
    ]
    good = [{"term": "ALFA", "definition": "significato di alfa"}]

    with agent.core_agent.override(model=_scripted_model([duplicate, good])):
        response = await agent.run(request)

    assert len(response.entries) == 1


async def test_a_valid_response_is_accepted_without_retry() -> None:
    agent = _agent()
    request = GlossaryExtractorRequest(block_text=_BLOCK_TEXT)
    good = [
        {"term": "ALFA", "definition": "significato di alfa"},
        {"term": "BETA", "definition": "significato di beta"},
    ]

    with agent.core_agent.override(model=_scripted_model([good])):
        response = await agent.run(request)

    assert [e.term for e in response.entries] == ["ALFA", "BETA"]
