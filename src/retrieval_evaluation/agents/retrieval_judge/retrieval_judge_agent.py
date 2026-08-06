from commons.ai.agents import BaseAgent

from .dto import RetrievalJudgeRequest, RetrievalJudgeResponse


class RetrievalJudgeAgent(BaseAgent[RetrievalJudgeRequest, RetrievalJudgeResponse]):
    """Pure LLM wrapper judging whether retrieved commas justify a quiz answer."""

    output_type = RetrievalJudgeResponse
