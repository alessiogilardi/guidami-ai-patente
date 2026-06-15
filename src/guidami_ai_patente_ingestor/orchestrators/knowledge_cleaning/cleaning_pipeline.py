import logging
from pathlib import Path

from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

logger = logging.getLogger(__name__)


class CleaningPipeline:
    """Pulisce il corpus `data/parsed/` e scrive `data/cleaned/`.

    Esegue la pulizia una sola volta: se l'output esiste già per una
    source, la salta.
    """

    def __init__(
        self,
        article_repository: ArticleRepository,
        article_cleaner: ArticleCleaner,
        config: IngestorConfig,
    ) -> None:
        """Inietta le dipendenze della pipeline e la configurazione."""
        self._article_repository = article_repository
        self._article_cleaner = article_cleaner
        self._config = config

    def run(self) -> None:
        """Pulisce CdS e CAP, una source alla volta."""
        self._clean_source(self._config.cds_parsed_path, self._config.cds_cleaned_path, "cds")
        self._clean_source(self._config.cap_parsed_path, self._config.cap_cleaned_path, "cap")

    def _clean_source(self, parsed_path: Path, cleaned_path: Path, source: str) -> None:
        if cleaned_path.exists():
            logger.info(f"{source}: {cleaned_path} already exists, skipping cleaning")
            return

        articles = self._article_repository.load(parsed_path)
        cleaned_articles = [self._article_cleaner.clean(article) for article in articles]
        self._article_repository.write(cleaned_articles, cleaned_path)
        logger.info(f"{source}: cleaned {len(cleaned_articles)} articles -> {cleaned_path}")
