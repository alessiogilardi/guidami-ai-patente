"""The one genuinely new AI component of spec 0012: the explanation writer."""

import logging

from pydantic_ai import ModelRetry, RunContext
from pywire import Autowired, agent

from commons.ai.agents import BaseAgent
from guidami_ai_patente.providers import LlmCallTrackerProvider, OpenRouterProviderComponent
from guidami_ai_patente.repositories import AgentConfigRepository

from .dto import ExplanationWriterRequest, ExplanationWriterResponse

_AGENT_NAME = "explanation_writer"

logger = logging.getLogger(__name__)


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

    Grounding (FR-10) is enforced here, not by `ExplanationService`: an out-of-range
    `cited_comma_numbers` ordinal raises `ModelRetry`, which pydantic-ai feeds back into
    the same conversation as corrective feedback before the next attempt — mirroring
    `CommaLabelerAgent._validate_comma_numbers` (spec 0014). `config.num_retries` is the
    one retry budget for both this and any structural output issue; the service no
    longer retries a citation itself, it only maps an exhausted `UnexpectedModelBehavior`
    to `ExplanationUnavailableError`/503.
    """

    output_type = ExplanationWriterResponse

    agent_configs: Autowired[AgentConfigRepository]
    open_router: Autowired[OpenRouterProviderComponent]
    tracker_provider: Autowired[LlmCallTrackerProvider]

    def __init__(self) -> None:
        """Loads the writer's prompt, builds the agent, and registers its validator."""
        super().__init__(
            config=self.agent_configs.load(_AGENT_NAME),
            provider=self.open_router.provider,
            tracker=self.tracker_provider.tracker,
        )
        self._agent.output_validator(self._validate_comma_numbers)

    def _validate_comma_numbers(
        self, ctx: RunContext[ExplanationWriterRequest], data: ExplanationWriterResponse
    ) -> ExplanationWriterResponse:
        """Retries an out-of-range ordinal instead of letting it reach the client (FR-10).

        `ctx.deps` is the same `ExplanationWriterRequest` the model was prompted with
        (threaded by `BaseAgent.run`/`run_sync`) — `len(ctx.deps.commas)` is exactly the
        bound `ExplanationService._call_writer` used to check after the fact.
        """
        max_commas = len(ctx.deps.commas)
        out_of_range = [n for n in data.cited_comma_numbers if not 1 <= n <= max_commas]
        if out_of_range:
            logger.warning(
                "Explanation writer cited out-of-range ordinal(s) %s (valid range: 1-%d)",
                out_of_range,
                max_commas,
            )
            # Italian: sent back into the writer's all-Italian conversation as retry
            # feedback (.claude/rules/code-conventions.md's "prompt-facing text"
            # exception, extended to output_validator retry messages by spec 0014).
            raise ModelRetry(
                f"Gli ordinali {out_of_range} non sono validi: sono stati presentati solo "
                f"{max_commas} commi. Scegli ordinali tra 1 e {max_commas}."
            )
        return data
