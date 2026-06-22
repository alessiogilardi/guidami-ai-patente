"""Step che assegna gli embedding ai KnowledgeChunk (con filtro repealed di dominio)."""

import logging
from typing import cast

from commons.entities.knowledge import KnowledgeChunk
from commons.flowstep import FlowContext, Step
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class EmbedChunksStep(Step):
    """Assegna gli embedding ai KnowledgeChunk presenti in `CHUNKS`.

    Comportamento repealed (invariante rispetto al baseline):
    - `embed_repealed=False` (default): solo i chunk non-repealed ricevono il vettore;
      i repealed restano con `embedding=None` ma sono **presenti** in `CHUNKS`.
    - `embed_repealed=True`: tutti i chunk vengono embeddati.

    Composizione pura: nessuna ereditarietà da `EmbedStep` generico.
    """

    def __init__(
        self,
        name: str,
        embedding_service: EmbeddingService,
        embed_repealed: bool,
    ) -> None:
        """Inietta il service di embedding e il flag repealed.

        Args:
            name: Nome univoco dello step nel flow.
            embedding_service: Service che calcola gli embedding in batch.
            embed_repealed: Se True, embeddita anche i chunk repealed.
        """
        super().__init__(name)
        self._embedding_service = embedding_service
        self._embed_repealed = embed_repealed

    def execute(self, context: FlowContext) -> None:
        """Legge `CHUNKS`, assegna i vettori (in place), ri-scrive `CHUNKS`.

        I chunk repealed non filtrati restano con `embedding=None` nella lista
        completa, che viene re-inserita in `CHUNKS` invariata in lunghezza.

        Args:
            context: Shared pipeline context.
        """
        chunks = cast(list[KnowledgeChunk], context.get(context_keys.CHUNKS))
        to_embed = chunks if self._embed_repealed else [c for c in chunks if not c.is_repealed]

        if to_embed:
            vectors = self._embedding_service.embed(to_embed)
            for chunk, vector in zip(to_embed, vectors, strict=True):
                chunk.embedding = vector

        logger.info(
            f"Embedded {len(to_embed)}/{len(chunks)} chunks "
            f"(embed_repealed={self._embed_repealed})"
        )
        context.put(context_keys.CHUNKS, chunks)

    def get_required_keys(self) -> set[str]:
        """Richiede `CHUNKS` in input."""
        return {context_keys.CHUNKS}

    def get_produced_keys(self) -> set[str]:
        """Ri-dichiara `CHUNKS`: aggiorna i chunk con embedding assegnato in place.

        Nota: FlowValidator emette un WARNING benigno 'Produced key overwrites
        an already available key' — atteso e non bloccante.
        """
        return {context_keys.CHUNKS}
