from typing import Literal

from pydantic import BaseModel


class EmbeddableChunkModel(BaseModel):
    """Modello intermedio per il calcolo dell'embedding di un chunk del corpus.

    Specchio di `KnowledgeChunk` (stessi campi): separato per disaccoppiare
    `embedded_text` (riservato alla pipeline) dall'entità di scrittura DB.
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
        """Testo usato per il calcolo dell'embedding.

        Concatena titolo, contesto (se presente) e testo del chunk, una parte
        per riga, scartando le parti vuote.
        """
        parts = [self.article_title, self.context, self.chunk_text]
        return "\n".join(part for part in parts if part)
