import logging

from openai import AsyncOpenAI
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.providers import Provider
from pywire import Autowired, agent

from commons.ai.agents import AgentConfig, BaseAgent
from commons.ai.observability import LlmCallTracker
from glossary.repositories import GlossaryAgentConfigRepository

from .dto import GlossaryDefinitionSimplifierRequest, GlossaryDefinitionSimplifierResponse

logger = logging.getLogger(__name__)

_AGENT_NAME = "glossary_definition_simplifier"


@agent
class GlossaryDefinitionSimplifierAgent(
    BaseAgent[GlossaryDefinitionSimplifierRequest, GlossaryDefinitionSimplifierResponse]
):
    """Rewrites a batch of verbatim legal definitions into plain Italian (spec 0022 FR-3).

    A separate agent from `GlossaryExtractorAgent`: the opposite invariant (rewriting is
    the entire job here, forbidden there) and a different validator (count match, not
    verbatim-substring).
    """

    output_type = GlossaryDefinitionSimplifierResponse

    agent_configs: Autowired[GlossaryAgentConfigRepository]
    provider_dep: Autowired[Provider[AsyncOpenAI]]
    tracker: Autowired[LlmCallTracker]

    def __init__(
        self,
        config: AgentConfig | None = None,
        provider: Provider[AsyncOpenAI] | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """Builds the underlying `pydantic_ai` agent, resolving collaborators as needed.

        `config`/`provider`/`tracker` are only ever passed directly in a test; `tracker`
        must be guarded exactly like the other two (see `GlossaryExtractorAgent` for why
        an unconditional `self.tracker` read raises `AttributeError` outside the container).
        """
        resolved_config = config if config is not None else self.agent_configs.load(_AGENT_NAME)
        resolved_provider = provider if provider is not None else self.provider_dep
        resolved_tracker = tracker if tracker is not None else self.tracker
        super().__init__(
            config=resolved_config, provider=resolved_provider, tracker=resolved_tracker
        )
        self._agent.output_validator(self._validate_count)

    def _validate_count(
        self,
        ctx: RunContext[GlossaryDefinitionSimplifierRequest],
        data: GlossaryDefinitionSimplifierResponse,
    ) -> GlossaryDefinitionSimplifierResponse:
        expected = len(ctx.deps.entries)
        actual = len(data.simplifications)
        if actual != expected:
            logger.warning("Simplification batch returned %d items, expected %d", actual, expected)
            raise ModelRetry(
                f"Hai restituito {actual} semplificazioni ma il lotto contiene {expected} "
                "definizioni. Restituisci esattamente una semplificazione per ogni "
                "definizione, nello stesso ordine."
            )
        return data
