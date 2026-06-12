from typing import Literal

from pydantic import BaseModel


class KnowledgeChunk(BaseModel):
    """Riga della tabella `knowledge_chunks` (vedi db/init.sql)."""

    source: Literal["cds", "cap"]
    article_number: str
    article_title: str
    comma_index: int
    chunk_text: str
    is_repealed: bool
    source_url: str
    embedding: list[float] | None = None
