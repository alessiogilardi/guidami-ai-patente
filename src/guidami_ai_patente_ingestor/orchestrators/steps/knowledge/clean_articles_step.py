"""Step che pulisce gli articoli parsed dal markup normattiva."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

logger = logging.getLogger(__name__)


class CleanArticlesStep(Step):
    """Pulisce gli articoli parsed dal markup normattiva.

    Step sottile: delega ogni articolo a `ArticleCleaner.clean`.
    """

    def __init__(self, name: str, article_cleaner: ArticleCleaner) -> None:
        """Inietta il cleaner di dominio.

        Args:
            name: Nome univoco dello step nel flow.
            article_cleaner: Servizio che pulisce un `Article` dal markup normattiva.
        """
        super().__init__(name)
        self._cleaner = article_cleaner

    def execute(self, context: FlowContext) -> None:
        """Legge `PARSED_ARTICLES`, pulisce e scrive `CLEANED_ARTICLES`.

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[Article], context.get(context_keys.PARSED_ARTICLES))
        cleaned = [self._cleaner.clean(article) for article in articles]

        logger.info(f"Cleaned {len(cleaned)} articles")
        context.put(context_keys.CLEANED_ARTICLES, cleaned)

    def get_required_keys(self) -> set[str]:
        """Richiede `PARSED_ARTICLES` in input."""
        return {context_keys.PARSED_ARTICLES}

    def get_produced_keys(self) -> set[str]:
        """Produce `CLEANED_ARTICLES`: lista piatta di Article puliti."""
        return {context_keys.CLEANED_ARTICLES}
