from typing import Literal

from pydantic import BaseModel


class KnowledgeChunk(BaseModel):
    """Riga della tabella `knowledge_chunks` (vedi db/init.sql)."""

    source: Literal["cds", "cap"]
    article_number: str
    article_title: str
    comma_index: int
    chunk_text: str
    context: str = ""
    is_repealed: bool
    source_url: str
    embedding: list[float] | None = None

    @property
    def embedded_text(self) -> str:
        """Testo usato per il calcolo dell'embedding (titolo + contesto + testo)."""
        parts = [self.article_title, self.context, self.chunk_text]
        return "\n".join(p for p in parts if p)
