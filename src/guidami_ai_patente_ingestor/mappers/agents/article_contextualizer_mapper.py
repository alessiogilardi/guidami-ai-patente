from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel


class ArticleContextualizerMapper:
    """Traduzione bidirezionale tra `EnrichedArticleModel` e i DTO dell'agente contestualizzatore.

    Tutti i metodi sono statici e puri (nessuna dipendenza iniettata).
    """

    @staticmethod
    def from_enriched_article_to_request(
        article: EnrichedArticleModel,
    ) -> ArticleContextualizerRequest:
        """Costruisce la request dell'agente a partire da un articolo enriched.

        Args:
            article: Articolo del corpus normativo da contestualizzare.

        Returns:
            `ArticleContextualizerRequest` con i commi pre-formattati come stringa numerata.
        """
        paragraphs = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(article.paragraphs))
        return ArticleContextualizerRequest(
            title=article.title,
            text=article.text,
            paragraphs=paragraphs,
        )

    @staticmethod
    def from_response_to_enriched_article(
        article: EnrichedArticleModel,
        response: ArticleContextualizerResponse,
    ) -> EnrichedArticleModel:
        """Applica i contesti prodotti dall'agente all'articolo enriched.

        Args:
            article: Articolo originale su cui applicare i contesti.
            response: Risposta strutturata dell'agente con i contesti per comma.

        Returns:
            Nuova `EnrichedArticleModel` con `contexts` valorizzato dalla response.
        """
        return article.model_copy(update={"contexts": response.contexts})
