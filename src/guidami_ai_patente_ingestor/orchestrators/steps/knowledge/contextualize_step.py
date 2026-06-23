"""Step che genera i contesti per comma e produce gli articoli enriched."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.mappers.knowledge import EnrichedArticleMapper
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class ContextualizeStep(Step):
    """Genera i contesti per comma via LLM e produce gli `EnrichedArticle`.

    Step sottile: delega ogni articolo a `ArticleContextualizerAgent.contextualize`
    e poi a `EnrichedArticleMapper` per assemblare l'`EnrichedArticle`.
    """

    def __init__(
        self, name: str, article_contextualizer_agent: ArticleContextualizerAgent
    ) -> None:
        """Inietta l'agente di contestualizzazione.

        Args:
            name: Nome univoco dello step nel flow.
            article_contextualizer_agent: Agente che genera i contesti per comma via LLM.
        """
        super().__init__(name)
        self._agent = article_contextualizer_agent

    def execute(self, context: FlowContext) -> None:
        """Legge `CLEANED_ARTICLES`, contestualizza e scrive `ENRICHED_ARTICLES`.

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[Article], context.get(context_keys.CLEANED_ARTICLES))
        enriched = [
            EnrichedArticleMapper.from_article_to_enriched_article(
                article, self._agent.contextualize(article)
            )
            for article in articles
        ]

        logger.info(f"Contextualized {len(enriched)} articles")
        context.put(context_keys.ENRICHED_ARTICLES, enriched)

    def get_required_keys(self) -> set[str]:
        """Richiede `CLEANED_ARTICLES` in input."""
        return {context_keys.CLEANED_ARTICLES}

    def get_produced_keys(self) -> set[str]:
        """Produce `ENRICHED_ARTICLES`: lista piatta di EnrichedArticle."""
        return {context_keys.ENRICHED_ARTICLES}
