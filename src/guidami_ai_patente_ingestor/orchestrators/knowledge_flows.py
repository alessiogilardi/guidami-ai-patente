"""Factory per il flow di knowledge indexing (SP03)."""

import logging

from commons.clients import EmbeddingClient, PostgresClient
from commons.flowstep import Flow, FlowBuilder
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.generic import DbStoreStep
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    ChunkArticlesStep,
    EmbedChunksStep,
    LoadEnrichedArticlesStep,
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
    validate: bool = False,
) -> Flow:
    """Assembla il flow di knowledge indexing (corpus → chunk → embed → store).

    Mappatura step:
      `LoadEnrichedArticlesStep` → `ChunkArticlesStep` → `EmbedChunksStep`
      → `DbStoreStep(items_key=CHUNKS)`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        embedding_client: Client per il calcolo degli embedding.
        postgres_client: Client Postgres per le operazioni sul DB.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR; il WARNING benigno su `CHUNKS`
            (EmbedChunksStep ri-dichiara una chiave già prodotta da ChunkArticlesStep)
            non blocca la build.

    Returns:
        Flow configurato e pronto per l'esecuzione.
    """
    indexing_config = config.knowledge_indexing

    load_step = LoadEnrichedArticlesStep(
        "load_enriched_articles",
        enriched_article_repository=EnrichedArticleRepository(),
        layer_resolver=layer_resolver,
        input_layer=indexing_config.input_layer,
        sources=indexing_config.sources,
    )

    chunk_step = ChunkArticlesStep(
        "chunk_articles",
        article_chunker=ArticleChunker(),
    )

    embed_step = EmbedChunksStep(
        "embed_chunks",
        embedding_service=EmbeddingService(embedding_client, config.embedding_batch_size),
        embed_repealed=config.embed_repealed,
    )

    store_step = DbStoreStep(
        "store_chunks",
        store_repo=KnowledgeChunkStoreRepository(postgres_client, config.knowledge_chunks_table),
        items_key=context_keys.CHUNKS,
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
