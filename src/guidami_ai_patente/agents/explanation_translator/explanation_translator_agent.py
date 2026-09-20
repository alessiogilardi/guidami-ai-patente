"""The translation agent introduced by spec 0018: IT -> RU for quiz explanations."""

from pywire import Autowired, agent

from commons.ai.agents import BaseAgent
from guidami_ai_patente.providers import LlmCallTrackerProvider, OpenRouterProviderComponent
from guidami_ai_patente.repositories import AgentConfigRepository

from .dto import ExplanationTranslatorRequest, ExplanationTranslatorResponse

_AGENT_NAME = "explanation_translator"


@agent
class ExplanationTranslatorAgent(
    BaseAgent[ExplanationTranslatorRequest, ExplanationTranslatorResponse]
):
    """Translates an already-produced Italian explanation to Russian (spec 0018).

    Mirrors `ExplanationWriterAgent`'s wiring exactly (spec 0018, AD-3): the same
    three `Autowired` providers, the same zero-arg `__init__` delegating to
    `BaseAgent`. `LlmCallTrackerProvider` is not optional — ADR 0031 requires every
    API-side agent to report through the shared tracker.
    """

    output_type = ExplanationTranslatorResponse

    agent_configs: Autowired[AgentConfigRepository]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Builds the underlying `pydantic_ai` agent from `explanation_translator.yaml`."""
        super().__init__(
            config=self.agent_configs.load(_AGENT_NAME),
            provider=self.open_router.provider,
            tracker=self.tracker_provider.tracker,
        )
