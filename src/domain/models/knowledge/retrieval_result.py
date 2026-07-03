from pydantic import BaseModel

from domain.entities.knowledge import KnowledgeChunk


class RetrievalResult(BaseModel):
    """Risultato di una similarity search sul vector store."""

    chunk: KnowledgeChunk
    score: float
