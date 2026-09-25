"""Tests for GlossaryEnricherAgent's wiring (FR-1, AD-3)."""

from dataclasses import dataclass

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from guidami_ai_patente.agents import GlossaryEnricherAgent
from guidami_ai_patente.agents.glossary_enricher.dto import GlossaryEnricherRequest

_PROVIDER = OpenRouterProvider(api_key="test-key")

_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Domanda: $text",
    num_retries=3,
)


@dataclass
class _AgentConfigRepositoryDouble:
    config: AgentConfig

    def load(self, name: str) -> AgentConfig:
        return self.config


@dataclass
class _OpenRouterProviderComponentDouble:
    provider: OpenRouterProvider


@dataclass
class _LlmCallTrackerProviderDouble:
    tracker: None = None


def _make_agent() -> GlossaryEnricherAgent:
    agent = object.__new__(GlossaryEnricherAgent)
    agent.agent_configs = _AgentConfigRepositoryDouble(_TEST_CONFIG)  # type: ignore[assignment]
    agent.open_router = _OpenRouterProviderComponentDouble(_PROVIDER)  # type: ignore[assignment]
    agent.tracker_provider = _LlmCallTrackerProviderDouble()  # type: ignore[assignment]
    agent.__init__()  # type: ignore[misc]
    return agent


def _model_returning(entries: list[dict[str, str]]) -> FunctionModel:
    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert info.output_tools
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {"entries": entries})])

    return FunctionModel(_func)


async def test_the_agent_returns_the_models_entries_unchanged() -> None:
    agent = _make_agent()
    request = GlossaryEnricherRequest(text="Cos'è la revoca?")

    with agent.core_agent.override(
        model=_model_returning([{"term": "revoca", "definition": "Definizione."}])
    ):
        response = await agent.run(request)

    assert response.entries[0].term == "revoca"
    assert response.entries[0].definition == "Definizione."


async def test_an_empty_comma_list_does_not_prevent_the_agent_from_running() -> None:
    """FR-2: find_with_vector returning None still lets the agent run and answer."""
    agent = _make_agent()
    request = GlossaryEnricherRequest(text="Domanda senza termini tecnici.", commas=[])

    with agent.core_agent.override(model=_model_returning([])):
        response = await agent.run(request)

    assert response.entries == []
