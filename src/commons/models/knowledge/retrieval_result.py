from pydantic import BaseModel

from .knowledge_chunk import KnowledgeChunk


class RetrievalResult(BaseModel):
    """Risultato di una similarity search sul vector store."""

    chunk: KnowledgeChunk
    score: float
