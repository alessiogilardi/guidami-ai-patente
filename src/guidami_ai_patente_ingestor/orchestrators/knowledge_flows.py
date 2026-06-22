"""Factory per il flow di knowledge indexing (SP03) — per-source."""

import logging
from typing import Literal, cast

from commons.clients import EmbeddingClient, PostgresClient
from commons.flowstep import Flow, FlowBuilder
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    ChunkArticlesStep,
    EmbedChunksStep,
    LoadEnrichedArticlesStep,
    StoreChunksStep,
)
from guidami_ai_patente_ingestor.repositories import (
    EnrichedArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

logger = logging.getLogger(__name__)


def build_knowledge_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    source: str,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di knowledge indexing per UNA source (corpus → chunk → embed → store).

    Il flow è per-source: va eseguito una volta per source (es. `cds`, poi `cap`).
    Lo store fa full-reload della sola source (delete-by-source + insert), quindi
    run su source diverse non si sovrascrivono.

    Mappatura step:
      `LoadEnrichedArticlesStep` → `ChunkArticlesStep` → `EmbedChunksStep`
      → `StoreChunksStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        embedding_client: Client per il calcolo degli embedding.
        postgres_client: Client Postgres per le operazioni sul DB.
        source: Source da indicizzare; deve appartenere a `config.knowledge_indexing.sources`.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR; il WARNING benigno su `CHUNKS`
            (EmbedChunksStep ri-dichiara una chiave già prodotta da ChunkArticlesStep)
            non blocca la build.

    Returns:
        Flow configurato e pronto per l'esecuzione.

    Raises:
        ValueError: se `source` non è tra le source valide configurate per l'indexing.
    """
    indexing_config = config.knowledge_indexing

    valid_sources = set(indexing_config.sources)
    if source not in valid_sources:
        raise ValueError(
            f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}"
        )
    typed_source = cast(Literal["cds", "cap"], source)

    load_step = LoadEnrichedArticlesStep(
        "load_enriched_articles",
        enriched_article_repository=EnrichedArticleRepository(),
        layer_resolver=layer_resolver,
        input_layer=indexing_config.input_layer,
        source=source,
    )

    chunk_step = ChunkArticlesStep(
        "chunk_articles",
        article_chunker=ArticleChunker(),
        source=typed_source,
    )

    embed_step = EmbedChunksStep(
        "embed_chunks",
        embedding_service=EmbeddingService(embedding_client, config.embedding_batch_size),
        embed_repealed=config.embed_repealed,
    )

    store_step = StoreChunksStep(
        "store_chunks",
        repository=KnowledgeChunkStoreRepository(postgres_client, config.knowledge_chunks_table),
        source=source,
    )

    flow: Flow = (
        FlowBuilder("knowledge_indexing")
        .add_step(load_step)
        .add_step(chunk_step)
        .add_step(embed_step)
        .add_step(store_step)
        .build(validate=validate)
    )

    return flow
