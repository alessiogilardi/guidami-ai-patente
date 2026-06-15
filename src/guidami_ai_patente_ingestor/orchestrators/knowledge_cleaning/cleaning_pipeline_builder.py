from typing import Self

from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

from .cleaning_pipeline import CleaningPipeline


class CleaningPipelineBuilder:
    """Valida `IngestorConfig` e assembla `CleaningPipeline` con le dipendenze concrete.

    Le dipendenze concrete possono essere sovrascritte tramite i metodi `with_*`
    (fluent), ad es. per iniettare fake/mock nei test senza toccare i moduli interni.
    """

    def __init__(self, config: IngestorConfig) -> None:
        """Memorizza la configurazione da cui costruire la pipeline."""
        self._config = config
        self._article_repository: ArticleRepository | None = None
        self._article_cleaner: ArticleCleaner | None = None

    def with_article_repository(self, article_repository: ArticleRepository) -> Self:
        """Sostituisce l'`ArticleRepository` di default."""
        self._article_repository = article_repository
        return self

    def with_article_cleaner(self, article_cleaner: ArticleCleaner) -> Self:
        """Sostituisce l'`ArticleCleaner` di default."""
        self._article_cleaner = article_cleaner
        return self

    def build(self) -> CleaningPipeline:
        """Verifica i path sorgente e assembla la pipeline."""
        self._validate_source_paths()
        return CleaningPipeline(
            article_repository=(
                self._article_repository
                if self._article_repository is not None
                else ArticleRepository()
            ),
            article_cleaner=(
                self._article_cleaner
                if self._article_cleaner is not None
                else ArticleCleaner()
            ),
            config=self._config,
        )

    def _validate_source_paths(self) -> None:
        missing = [
            path
            for path in (self._config.cds_parsed_path, self._config.cap_parsed_path)
            if not path.exists()
        ]
        if missing:
            paths = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"File sorgente non trovato: {paths}")
