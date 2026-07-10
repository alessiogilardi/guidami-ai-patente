from commons.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)


class ArticleContextualizerAgent(
    BaseAgent[ArticleContextualizerRequest, ArticleContextualizerResponse]
):
    """Pure LLM wrapper for contextualising normative articles."""

    output_type = ArticleContextualizerResponse
