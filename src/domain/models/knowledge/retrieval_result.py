from pydantic import BaseModel

from domain.entities.knowledge import KnowledgeChunk


class RetrievalResult(BaseModel):
    """Result of a similarity search on the vector store."""

    chunk: KnowledgeChunk
    score: float
