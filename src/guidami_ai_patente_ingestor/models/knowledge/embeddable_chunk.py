from typing import Literal

from pydantic import BaseModel


class EmbeddableChunkModel(BaseModel):
    """Intermediate model for computing the embedding of a corpus chunk.

    Mirrors `KnowledgeChunk` (same fields): kept separate to decouple
    `embedded_text` (reserved for the pipeline) from the DB write entity.
    """

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
        """Text used for computing the embedding.

        Concatenates title, context (if present), and chunk text, one part
        per line, discarding empty parts.
        """
        parts = [self.article_title, self.context, self.chunk_text]
        return "\n".join(part for part in parts if part)
