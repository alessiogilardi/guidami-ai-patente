from commons.ai.agents import BaseAgent

from .dto import CommaLabelerRequest, CommaLabelerResponse


class CommaLabelerAgent(BaseAgent[CommaLabelerRequest, CommaLabelerResponse]):
    """Pure LLM wrapper labeling which candidate commas justify a quiz answer."""

    output_type = CommaLabelerResponse
