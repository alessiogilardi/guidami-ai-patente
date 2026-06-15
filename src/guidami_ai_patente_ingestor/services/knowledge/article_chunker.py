from typing import Literal

from commons.models.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.entities import Article


class ArticleChunker:
    """Trasforma un `Article` in `KnowledgeChunk` (uno per comma, senza embedding)."""

    def chunk(self, article: Article, source: Literal["cds", "cap"]) -> list[KnowledgeChunk]:
        """Genera i chunk di `article`: comma 0 da `text` (se non vuoto) + uno per paragrafo."""
        chunks: list[KnowledgeChunk] = []

        if article.text:
            chunks.append(
                self._build_chunk(article, source, comma_index=0, raw_text=article.text)
            )

        for comma_index, paragraph in enumerate(article.paragraphs, start=1):
            chunks.append(
                self._build_chunk(article, source, comma_index=comma_index, raw_text=paragraph)
            )

        return chunks

    def _build_chunk(
        self, article: Article, source: Literal["cds", "cap"], comma_index: int, raw_text: str
    ) -> KnowledgeChunk:
        return KnowledgeChunk(
            source=source,
            article_number=article.number,
            article_title=article.title,
            comma_index=comma_index,
            chunk_text=raw_text,
            is_repealed=article.repealed or "ABROGAT" in raw_text.upper(),
            source_url=article.url,
        )
