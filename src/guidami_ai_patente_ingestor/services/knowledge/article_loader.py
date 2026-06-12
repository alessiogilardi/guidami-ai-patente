import json
from pathlib import Path

from guidami_ai_patente_ingestor.entities import Article


class ArticleLoader:
    """Carica gli articoli del corpus normativo da un file JSON."""

    def load(self, path: Path) -> list[Article]:
        """Legge `path` e mappa ogni elemento in un `Article`."""
        raw_articles = json.loads(path.read_text(encoding="utf-8"))
        return [Article.model_validate(raw_article) for raw_article in raw_articles]
