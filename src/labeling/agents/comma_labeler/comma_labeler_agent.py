import logging

from openai import AsyncOpenAI
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.providers import Provider

from commons.ai.agents import AgentConfig, BaseAgent
from commons.ai.observability import LlmCallTracker
from commons.clients import FileReaderInterface

from .dto import CommaLabelerRequest, CommaLabelerResponse

logger = logging.getLogger(__name__)


class CommaLabelerAgent(BaseAgent[CommaLabelerRequest, CommaLabelerResponse]):
    """Pure LLM wrapper labeling which candidate commas justify a quiz answer."""

    output_type = CommaLabelerResponse

    def __init__(
        self,
        config: AgentConfig,
        provider: Provider[AsyncOpenAI],
        file_reader: FileReaderInterface | None = None,
        tracker: LlmCallTracker | None = None,
    ) -> None:
        """Registers the out-of-range ordinal validator on the wrapped agent."""
        super().__init__(config, provider, file_reader, tracker)
        self._agent.output_validator(self._validate_comma_numbers)

    def _validate_comma_numbers(
        self, ctx: RunContext[CommaLabelerRequest], data: CommaLabelerResponse
    ) -> CommaLabelerResponse:
        """Retries an out-of-range ordinal instead of letting it reach the write path.

        `ctx.deps` is the same `CommaLabelerRequest` the model was prompted with
        (threaded by `BaseAgent.run`/`run_sync`, spec 0014 FR-1) — `len(ctx.deps.candidates)`
        is exactly the bound `QuestionLabelingService._resolve_labels` checks after the
        fact today, available here before that check would ever fail.
        """
        max_candidates = len(ctx.deps.candidates)
        out_of_range = [n for n in data.comma_numbers if not 1 <= n <= max_candidates]
        if out_of_range:
            logger.warning(
                "Comma labeler returned out-of-range ordinal(s) %s (valid range: 1-%d)",
                out_of_range,
                max_candidates,
            )
            # Italian: sent back into comma-labeler's all-Italian conversation as retry
            # feedback (.claude/rules/code-conventions.md's "prompt-facing text" exception,
            # extended to output_validator retry messages by spec 0014).
            raise ModelRetry(
                f"Gli ordinali {out_of_range} non sono validi: sono stati presentati solo "
                f"{max_candidates} commi. Scegli ordinali tra 1 e {max_candidates}."
            )
        return data
