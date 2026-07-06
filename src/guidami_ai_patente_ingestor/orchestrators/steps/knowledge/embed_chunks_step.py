"""Step che assegna gli embedding agli EmbeddableChunkModel (con filtro repealed di dominio)."""

import logging
from typing import cast

from commons.services.embeddings import EmbeddingService
from flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class EmbedChunksStep(Step):
    """Assegna gli embedding agli EmbeddableChunkModel presenti in `EMBEDDABLE_CHUNKS`.

    Comportamento repealed (invariante rispetto al baseline):
    - `embed_repealed=False` (default): solo i chunk non-repealed ricevono il vettore;
      i repealed restano con `embedding=None` ma sono **presenti** in `EMBEDDABLE_CHUNKS`.
    - `embed_repealed=True`: tutti i chunk vengono embeddati.

    Composizione pura: nessuna ereditarietà da `EmbedStep` generico.
    """

    def __init__(
        self,
        name: str,
        embed_repealed: bool,
        embedding_service: EmbeddingService,
    ) -> None:
        """Inietta il flag repealed e il service di embedding.

        Args:
            name: Nome univoco dello step nel flow.
            embed_repealed: Se True, embeddita anche i chunk repealed.
            embedding_service: Service che calcola gli embedding in batch.
        """
        super().__init__(name)
        self._embed = embedding_service
        self._embed_repealed = embed_repealed

    def execute(self, context: FlowContext) -> None:
        """Legge `EMBEDDABLE_CHUNKS`, assegna i vettori (in place), ri-scrive `EMBEDDABLE_CHUNKS`.

        I chunk repealed non filtrati restano con `embedding=None` nella lista
        completa, che viene re-inserita in `EMBEDDABLE_CHUNKS` invariata in lunghezza.

        Args:
            context: Shared pipeline context.
        """
        chunks = cast(list[EmbeddableChunkModel], context.get(context_keys.EMBEDDABLE_CHUNKS))
        to_embed = chunks if self._embed_repealed else [c for c in chunks if not c.is_repealed]

        if to_embed:
            vectors = self._embed(to_embed)
            for chunk, vector in zip(to_embed, vectors, strict=True):
                chunk.embedding = vector

        logger.info(
            f"Embedded {len(to_embed)}/{len(chunks)} chunks "
            f"(embed_repealed={self._embed_repealed})"
        )
        context.put(context_keys.EMBEDDABLE_CHUNKS, chunks)

    def get_required_keys(self) -> set[str]:
        """Richiede `EMBEDDABLE_CHUNKS` in input."""
        return {context_keys.EMBEDDABLE_CHUNKS}

    def get_produced_keys(self) -> set[str]:
        """Ri-dichiara `EMBEDDABLE_CHUNKS`: aggiorna i chunk con embedding assegnato in place.

        Nota: FlowValidator emette un WARNING benigno 'Produced key overwrites
        an already available key' — atteso e non bloccante.
        """
        return {context_keys.EMBEDDABLE_CHUNKS}
