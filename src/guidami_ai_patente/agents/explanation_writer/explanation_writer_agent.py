"""The one genuinely new AI component of spec 0012: the explanation writer."""

from pywire import Autowired, agent

from commons.ai.agents import BaseAgent
from guidami_ai_patente.providers import LlmCallTrackerProvider, OpenRouterProviderComponent
from guidami_ai_patente.repositories import AgentConfigRepository

from .dto import ExplanationWriterRequest, ExplanationWriterResponse

_AGENT_NAME = "explanation_writer"


@agent
class ExplanationWriterAgent(BaseAgent[ExplanationWriterRequest, ExplanationWriterResponse]):
    """Renders a grounded explanation from the commas a labeling associated (FR-10).

    Pywire-native despite `BaseAgent` needing a real constructor: pywire sets every
    `Autowired` field *before* calling this class's own `__init__` (ADR 0017/0023), so
    a zero-argument `__init__` can read them and delegate to `super()`.

    Its prompt is loaded through `AgentConfigRepository.load` — the **non-epoch**
    anchor (D4). The writer's prompt enters no configuration epoch by design: AD-7
    rebuilds the explanation on every request precisely so the wording can evolve
    without invalidating a single cached labeling.

    Calls are recorded through the shared tracker (D5), so the live path's latency,
    tokens and cost are observable in the same place the batch pass's are.
    """

    output_type = ExplanationWriterResponse

    agent_configs: Autowired[AgentConfigRepository]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Loads the writer's prompt and builds the underlying pydantic-ai agent."""
        super().__init__(
            config=self.agent_configs.load(_AGENT_NAME),
            provider=self.open_router.provider,
            tracker=self.tracker_provider.tracker,
        )
