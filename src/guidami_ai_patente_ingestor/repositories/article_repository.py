import json
from pathlib import Path

from guidami_ai_patente_ingestor.entities import Article


class ArticleRepository:
    """Legge e scrive il corpus normativo (CdS/CAP) da/verso file JSON."""

    def load(self, path: Path) -> list[Article]:
        """Legge `path` e mappa ogni elemento in un `Article`."""
        raw_articles = json.loads(path.read_text(encoding="utf-8"))
        return [Article.model_validate(raw_article) for raw_article in raw_articles]

    def write(self, articles: list[Article], path: Path) -> None:
        """Crea le directory mancanti e scrive `articles` come JSON in `path`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [article.model_dump() for article in articles]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
