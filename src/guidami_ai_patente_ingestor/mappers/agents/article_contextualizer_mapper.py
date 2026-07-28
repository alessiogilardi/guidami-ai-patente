from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel


class ArticleContextualizerMapper:
    """Bidirectional translation between `EnrichedArticleModel` and the contextualizer agent DTOs.

    All methods are static and pure (no injected dependencies).
    """

    @staticmethod
    def from_enriched_article_to_request(
        article: EnrichedArticleModel,
    ) -> ArticleContextualizerRequest:
        """Builds the agent request from an enriched article.

        Args:
            article: Article of the corpus normativo to contextualize.

        Returns:
            `ArticleContextualizerRequest` with the article's paragraphs.
        """
        return ArticleContextualizerRequest(
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
        )

    @staticmethod
    def from_response_to_enriched_article(
        article: EnrichedArticleModel,
        response: ArticleContextualizerResponse,
    ) -> EnrichedArticleModel:
        """Applies the contexts produced by the agent to the enriched article.

        Args:
            article: Original article to apply the contexts to.
            response: Structured agent response with the contexts per comma.

        Returns:
            New `EnrichedArticleModel` with `contexts` populated from the response.
        """
        return article.model_copy(update={"contexts": response.contexts})
