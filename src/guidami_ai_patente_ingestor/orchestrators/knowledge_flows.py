"""Factories for the knowledge preparation (SP05) and indexing (SP03) flows — per-source."""

import logging
from typing import Literal, cast

from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep

from commons.clients import EmbeddingClient, PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.configs import AgentConfig
from commons.repositories import JsonRepository, YamlRepository
from commons.services.embeddings import EmbeddingService
from commons.use_cases import FlatMap, ForEach
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel, ParsedArticleModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    EmbedChunksStep,
    StoreChunksStep,
)
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleCleaner
from guidami_ai_patente_ingestor.services.knowledge.enrichers import ContextEnricher

from .steps.generic import LoadJsonStep, WriteJsonStep

logger = logging.getLogger(__name__)

# Intermediate layer shared by the two preparation factories (clean/enrich):
# not expressed in PipelineLayerConfig (see the layer decision in SP05).
_CLEANED_LAYER = "cleaned"


def build_knowledge_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    source: str,
    validate: bool = False,
) -> Flow:
    """Assembles the knowledge indexing flow for ONE source (corpus → chunk → embed → store).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    The store performs a full-reload of that source only (delete-by-source + insert),
    so runs on different sources do not overwrite each other.

    Step mapping:
      `LoadJsonStep` → `ApplyStep` (chunk_articles, `FlatMap(ArticleChunker)`)
      → `EmbedChunksStep` → `ApplyStep` (map_to_chunk_entity) → `StoreChunksStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        embedding_client: Client for computing embeddings.
        postgres_client: Postgres client for DB operations.
        source: Source to index; must belong to `config.knowledge_indexing.sources`.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR; the benign WARNING on `EMBEDDABLE_CHUNKS`
            (EmbedChunksStep re-declares a key already produced by the chunk_articles step)
            does not block the build.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `source` is not among the valid sources configured for indexing.
    """
    indexing_config = config.knowledge_indexing

    valid_sources = set(indexing_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")
    typed_source = cast(Literal["cds", "cap"], source)

    load_step = LoadJsonStep(
        "load_enriched_articles",
        layer_resolver=layer_resolver,
        input_layer=indexing_config.input_layer,
        source=source,
        repository=JsonRepository.get_instance(
            EnrichedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
        output_key=context_keys.ENRICHED_ARTICLES,
    )

    chunk_step = ApplyStep(
        "chunk_articles",
        FlatMap(ArticleChunker(typed_source)),
        input_key=context_keys.ENRICHED_ARTICLES,
        output_key=context_keys.EMBEDDABLE_CHUNKS,
    )

    embed_step = EmbedChunksStep(
        "embed_chunks",
        embedding_service=EmbeddingService(config.embedding_batch_size, embedding_client),
        embed_repealed=config.embed_repealed,
    )

    map_to_entity_step = ApplyStep(
        "map_to_chunk_entity",
        ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk),
        input_key=context_keys.EMBEDDABLE_CHUNKS,
        output_key=context_keys.CHUNK_ENTITIES,
    )

    store_step = StoreChunksStep(
        "store_chunks",
        source=source,
        repository=KnowledgeChunkStoreRepository(config.knowledge_chunks_table, postgres_client),
    )

    flow: Flow = (
        FlowBuilder("knowledge_indexing")
        .add_step(load_step)
        .add_step(chunk_step)
        .add_step(embed_step)
        .add_step(map_to_entity_step)
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
    """Assembles the knowledge cleaning flow for ONE source (parsed → cleaned).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    No embed/store: this flow belongs to the preparation stage.

    Step mapping:
      `LoadJsonStep` → `ApplyStep` → `WriteJsonStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        source: Source to clean; must belong to `config.knowledge_preparation.sources`.
        validate: If True, runs structural validation of the flow before returning it.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `source` is not among the valid sources configured for preparation.
    """
    preparation_config = config.knowledge_preparation

    valid_sources = set(preparation_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    articles_repository = JsonRepository.get_instance(
        ParsedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
    )

    load_step = LoadJsonStep(
        "load_parsed_articles",
        layer_resolver=layer_resolver,
        input_layer=preparation_config.input_layer,
        source=source,
        repository=articles_repository,
        output_key=context_keys.PARSED_ARTICLES,
    )

    clean_step = ApplyStep(
        "clean_articles",
        ForEach(ArticleCleaner()),
        input_key=context_keys.PARSED_ARTICLES,
        output_key=context_keys.CLEANED_ARTICLES,
    )

    write_step = WriteJsonStep(
        "write_cleaned",
        layer_resolver=layer_resolver,
        output_layer=_CLEANED_LAYER,
        source=source,
        repository=articles_repository,
        input_key=context_keys.CLEANED_ARTICLES,
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
    """Assembles the knowledge enrichment flow for ONE source (cleaned → enriched).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    No embed/store: this flow belongs to the preparation stage.

    Step mapping:
      `LoadJsonStep` → `ApplyStep` → `WriteJsonStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        source: Source to enrich; must belong to `config.knowledge_preparation.sources`.
        validate: If True, runs structural validation of the flow before returning it.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `source` is not among the valid sources configured for preparation.
    """
    preparation_config = config.knowledge_preparation

    valid_sources = set(preparation_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    if preparation_config.output_layer is None:
        raise ValueError("knowledge_preparation.output_layer is not configured")

    load_step = LoadJsonStep(
        "load_cleaned_articles",
        layer_resolver=layer_resolver,
        input_layer=_CLEANED_LAYER,
        source=source,
        repository=JsonRepository.get_instance(
            ParsedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
        output_key=context_keys.CLEANED_ARTICLES,
    )

    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_repository)
    enrich_step = ApplyStep(
        "enrich",
        ForEach(ArticleMapper.from_parsed_to_enriched),
        ContextEnricher(agent),
        input_key=context_keys.CLEANED_ARTICLES,
        output_key=context_keys.ENRICHED_ARTICLES,
    )

    write_step = WriteJsonStep(
        "write_enriched",
        layer_resolver=layer_resolver,
        output_layer=preparation_config.output_layer,
        source=source,
        repository=JsonRepository.get_instance(
            EnrichedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
        input_key=context_keys.ENRICHED_ARTICLES,
    )

    flow: Flow = (
        FlowBuilder("knowledge_enrichment")
        .add_step(load_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow
