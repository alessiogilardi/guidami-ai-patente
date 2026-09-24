import logging

from openai import AsyncOpenAI
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.providers import Provider
from pywire import Autowired, agent

from commons.ai.agents import AgentConfig, BaseAgent
from commons.ai.observability import LlmCallTracker
from glossary.repositories import GlossaryAgentConfigRepository

from .dto import GlossaryExtractorRequest, GlossaryExtractorResponse

logger = logging.getLogger(__name__)

_AGENT_NAME = "glossary_extractor"


@agent
class GlossaryExtractorAgent(BaseAgent[GlossaryExtractorRequest, GlossaryExtractorResponse]):
    """Extracts term/definition pairs from one block's text, verbatim (FR-3, AD-2).

    The model may only select and split the normative text, never rewrite it: the
    `output_validator` rejects a non-verbatim definition, an absent term, or a
    repeated term, following `CommaLabelerAgent`'s precedent (spec 0014).
    """

    output_type = GlossaryExtractorResponse

    agent_configs: Autowired[GlossaryAgentConfigRepository]
    provider_dep: Autowired[Provider[AsyncOpenAI]]
    tracker: Autowired[LlmCallTracker]

    def __init__(
        self,
        config: AgentConfig | None = None,
        provider: Provider[AsyncOpenAI] | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """`config`/`provider`/`tracker` are only ever passed directly in a test; pywire
        resolution loads them from the autowired collaborators instead. `tracker` must be
        guarded exactly like the other two — accessing `self.tracker` unconditionally would
        raise `AttributeError` for an instance built outside the pywire container, since
        `Autowired[T]` is a plain annotation, not a descriptor.
        """
        resolved_config = config if config is not None else self.agent_configs.load(_AGENT_NAME)
        resolved_provider = provider if provider is not None else self.provider_dep
        resolved_tracker = tracker if tracker is not None else self.tracker
        super().__init__(
            config=resolved_config, provider=resolved_provider, tracker=resolved_tracker
        )
        self._agent.output_validator(self._validate_verbatim)

    def _validate_verbatim(
        self, ctx: RunContext[GlossaryExtractorRequest], data: GlossaryExtractorResponse
    ) -> GlossaryExtractorResponse:
        normalized_block = _normalize(ctx.deps.block_text)
        seen_terms: set[str] = set()
        for entry in data.entries:
            if _normalize(entry.definition) not in normalized_block:
                logger.warning("Non-verbatim definition rejected for term %r", entry.term)
                raise ModelRetry(
                    f'La definizione di "{entry.term}" non è presente verbatim nel testo. '
                    "Copia il testo esattamente, senza riformularlo."
                )
            if not entry.term.strip() or _normalize(entry.term) not in normalized_block:
                logger.warning("Absent term %r rejected", entry.term)
                raise ModelRetry(
                    f'Il termine "{entry.term}" non compare nel testo fornito. '
                    "Usa solo termini che compaiono letteralmente nel testo."
                )
            term_key = entry.term.casefold()
            if term_key in seen_terms:
                logger.warning("Duplicate term %r rejected", entry.term)
                raise ModelRetry(
                    f'Il termine "{entry.term}" è stato restituito più di una volta. '
                    "Ogni termine deve comparire una sola volta."
                )
            seen_terms.add(term_key)
        return data


def _normalize(text: str) -> str:
    return " ".join(text.split())
