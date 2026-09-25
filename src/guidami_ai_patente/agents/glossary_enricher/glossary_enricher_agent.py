"""The on-demand glossary enrichment agent (spec 0021): answer-blind term generation."""

from pywire import Autowired, agent

from commons.ai.agents import BaseAgent
from guidami_ai_patente.providers import LlmCallTrackerProvider, OpenRouterProviderComponent
from guidami_ai_patente.repositories import AgentConfigRepository

from .dto import GlossaryEnricherRequest, GlossaryEnricherResponse

_AGENT_NAME = "glossary_enricher"


@agent
class GlossaryEnricherAgent(BaseAgent[GlossaryEnricherRequest, GlossaryEnricherResponse]):
    """Generates glossary candidates for a question's terms, live, on every call (FR-1).

    Pywire-native, mirroring `QuestionExplainerAgent`'s wiring exactly. Unsuffixed
    config name: Italian output, the project's base language
    (`.claude/rules/agent-config-naming.md`).

    Unlike `QuestionExplainerAgent`, it needs no `output_validator`: its only
    structural invariant — no repeated normalized term within one response — is fully
    self-contained in `GlossaryEnricherResponse`'s own `model_validator`, which needs no
    `RunContext` (AD-3). Grounding vs. general-knowledge fallback (FR-3) is a
    prompt-level instruction, not mechanically enforced here, mirroring
    `question_explainer.yaml`'s own equivalent allowance.
    """

    output_type = GlossaryEnricherResponse

    agent_configs: Autowired[AgentConfigRepository]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Loads the enrichment prompt and builds the agent."""
        super().__init__(
            config=self.agent_configs.load(_AGENT_NAME),
            provider=self.open_router.provider,
            tracker=self.tracker_provider.tracker,
        )
