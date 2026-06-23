"""Factory per i flow di knowledge preparation (SP05) e indexing (SP03) — per-source."""

import logging
from typing import Literal, cast

from commons.clients import EmbeddingClient, PostgresClient
from commons.flowstep import Flow, FlowBuilder
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    ChunkArticlesStep,
    CleanArticlesStep,
    ContextualizeStep,
    EmbedChunksStep,
    LoadCleanedArticlesStep,
    LoadEnrichedArticlesStep,
    LoadParsedArticlesStep,
    StoreChunksStep,
    WriteCleanedStep,
    WriteEnrichedStep,
)
from guidami_ai_patente_ingestor.repositories import (
    ArticleRepository,
    EnrichedArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleCleaner

logger = logging.getLogger(__name__)

# Layer intermedio condiviso dalle due factory di preparation (clean/enrich):
# non espresso in PipelineLayerConfig (vedi decisione di layer in SP05).
_CLEANED_LAYER = "cleaned"


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
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")
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


def build_knowledge_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di knowledge cleaning per UNA source (parsed → cleaned).

    Il flow è per-source: va eseguito una volta per source (es. `cds`, poi `cap`).
    Nessun embed/store: questo flow appartiene allo stadio di preparazione.

    Mappatura step:
      `LoadParsedArticlesStep` → `CleanArticlesStep` → `WriteCleanedStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        source: Source da pulire; deve appartenere a `config.knowledge_preparation.sources`.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.

    Returns:
        Flow configurato e pronto per l'esecuzione.

    Raises:
        ValueError: se `source` non è tra le source valide configurate per la preparation.
    """
    preparation_config = config.knowledge_preparation

    valid_sources = set(preparation_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    load_step = LoadParsedArticlesStep(
        "load_parsed_articles",
        article_repository=ArticleRepository(),
        layer_resolver=layer_resolver,
        input_layer=preparation_config.input_layer,
        source=source,
    )

    clean_step = CleanArticlesStep("clean_articles", article_cleaner=ArticleCleaner())

    write_step = WriteCleanedStep(
        "write_cleaned",
        article_repository=ArticleRepository(),
        layer_resolver=layer_resolver,
        output_layer=_CLEANED_LAYER,
        source=source,
    )

    flow: Flow = (
        FlowBuilder("knowledge_cleaning")
        .add_step(load_step)
        .add_step(clean_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow


def build_knowledge_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di knowledge enrichment per UNA source (cleaned → enriched).

    Il flow è per-source: va eseguito una volta per source (es. `cds`, poi `cap`).
    Nessun embed/store: questo flow appartiene allo stadio di preparazione.

    Mappatura step:
      `LoadCleanedArticlesStep` → `ContextualizeStep` → `WriteEnrichedStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        source: Source da arricchire; deve appartenere a `config.knowledge_preparation.sources`.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.

    Returns:
        Flow configurato e pronto per l'esecuzione.

    Raises:
        ValueError: se `source` non è tra le source valide configurate per la preparation.
    """
    preparation_config = config.knowledge_preparation

    valid_sources = set(preparation_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    if preparation_config.output_layer is None:
        raise ValueError("knowledge_preparation.output_layer is not configured")

    load_step = LoadCleanedArticlesStep(
        "load_cleaned_articles",
        article_repository=ArticleRepository(),
        layer_resolver=layer_resolver,
        input_layer=_CLEANED_LAYER,
        source=source,
    )

    contextualize_step = ContextualizeStep(
        "contextualize",
        article_contextualizer_agent=ArticleContextualizerAgent.from_yaml(
            "article_contextualizer", config.agents_dir
        ),
    )

    write_step = WriteEnrichedStep(
        "write_enriched",
        enriched_article_repository=EnrichedArticleRepository(),
        layer_resolver=layer_resolver,
        output_layer=preparation_config.output_layer,
        source=source,
    )

    flow: Flow = (
        FlowBuilder("knowledge_enrichment")
        .add_step(load_step)
        .add_step(contextualize_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow
