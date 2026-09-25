import logging

from openai import AsyncOpenAI
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.providers import Provider
from pywire import Autowired, agent

from commons.ai.agents import AgentConfig, BaseAgent
from commons.ai.observability import LlmCallTracker
from glossary.repositories import GlossaryAgentConfigRepository

from .dto import GlossaryTermTranslatorRequest, GlossaryTermTranslatorResponse

logger = logging.getLogger(__name__)

_AGENT_NAME = "glossary_term_translator.ru"


@agent
class GlossaryTermTranslatorAgent(
    BaseAgent[GlossaryTermTranslatorRequest, GlossaryTermTranslatorResponse]
):
    """Translates a batch of Italian terms to Russian, term only (FR-4, AD-9).

    A separate agent from `GlossaryExtractorAgent`: different validator (count match,
    not verbatim-substring), different failure semantics (AD-11), different batching.
    """

    output_type = GlossaryTermTranslatorResponse

    agent_configs: Autowired[GlossaryAgentConfigRepository]
    provider_dep: Autowired[Provider[AsyncOpenAI]]
    tracker: Autowired[LlmCallTracker]

    def __init__(
        self,
        config: AgentConfig | None = None,
        provider: Provider[AsyncOpenAI] | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """`config`/`provider`/`tracker` are only ever passed directly in a test; `tracker`
        must be guarded exactly like the other two (see `GlossaryExtractorAgent`, Task 5, for
        why an unconditional `self.tracker` read raises `AttributeError` outside the container).
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
        ctx: RunContext[GlossaryTermTranslatorRequest],
        data: GlossaryTermTranslatorResponse,
    ) -> GlossaryTermTranslatorResponse:
        expected = len(ctx.deps.entries)
        actual = len(data.translations)
        if actual != expected:
            logger.warning("Translation batch returned %d items, expected %d", actual, expected)
            raise ModelRetry(
                f"Hai restituito {actual} traduzioni ma il lotto contiene {expected} termini. "
                "Restituisci esattamente una traduzione per ogni termine, nello stesso ordine."
            )
        return data
