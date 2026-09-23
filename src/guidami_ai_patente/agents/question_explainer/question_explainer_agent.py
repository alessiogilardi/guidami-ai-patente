"""The vocabulary explanation agent (spec 0020): answer-blind term grounding."""

import logging

from pydantic_ai import ModelRetry, RunContext
from pywire import Autowired, agent

from commons.ai.agents import BaseAgent
from guidami_ai_patente.providers import LlmCallTrackerProvider, OpenRouterProviderComponent
from guidami_ai_patente.repositories import AgentConfigRepository

from .dto import QuestionExplainerRequest, QuestionExplainerResponse

_AGENT_NAME = "question_explainer"

logger = logging.getLogger(__name__)


@agent
class QuestionExplainerAgent(BaseAgent[QuestionExplainerRequest, QuestionExplainerResponse]):
    """Explains a question's own wording and technical terms, answer-blind (FR-2, FR-6).

    Pywire-native, mirroring `ExplanationWriterAgent`'s wiring exactly. Unsuffixed config
    name: Italian output, the project's base language
    (`.claude/rules/agent-config-naming.md`) — Russian happens afterward, on the whole
    merged message, via the existing translator (spec 0018).

    Grounding (FR-6) is enforced by its own `output_validator`, mirroring
    `CommaLabelerAgent` (spec 0014) and the migrated `ExplanationWriterAgent` (AD-8) —
    not by `ExplanationService`.
    """

    output_type = QuestionExplainerResponse

    agent_configs: Autowired[AgentConfigRepository]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Loads the vocabulary prompt, builds the agent, registers its validator."""
        super().__init__(
            config=self.agent_configs.load(_AGENT_NAME),
            provider=self.open_router.provider,
            tracker=self.tracker_provider.tracker,
        )
        self._agent.output_validator(self._validate_term_numbers)

    def _validate_term_numbers(
        self, ctx: RunContext[QuestionExplainerRequest], data: QuestionExplainerResponse
    ) -> QuestionExplainerResponse:
        """Retries an out-of-range ordinal instead of letting it reach the client (FR-6)."""
        max_candidates = len(ctx.deps.candidates)
        out_of_range = [n for n in data.cited_term_numbers if not 1 <= n <= max_candidates]
        if out_of_range:
            logger.warning(
                "Question explainer cited out-of-range ordinal(s) %s (valid range: 1-%d)",
                out_of_range,
                max_candidates,
            )
            raise ModelRetry(
                f"Gli ordinali {out_of_range} non sono validi: sono stati presentati solo "
                f"{max_candidates} candidati. Scegli ordinali tra 1 e {max_candidates}, "
                "oppure non citarne nessuno."
            )
        return data
