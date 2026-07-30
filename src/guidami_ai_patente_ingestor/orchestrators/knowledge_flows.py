"""Factories for the knowledge preparation (SP05) and indexing (SP03) flows — per-source."""

import logging
from functools import partial
from typing import Literal, cast

from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep, AsyncApplyStep
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.embedding import EmbeddingClient, EmbeddingService
from commons.ai.observability import LlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import JsonRepository, YamlRepository
from commons.use_cases import FlatMap, ForEach
from commons.utils import element_id
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import (
    CleanedArticleModel,
    EnrichedArticleModel,
    ParsedArticleModel,
)
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    EmbedChunksStep,
    StoreChunksStep,
)
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleCleaner
from guidami_ai_patente_ingestor.services.knowledge.enrichers import ContextEnricher

from .steps.generic import (
    FilterAlreadyDoneStep,
    LoadJsonDirStep,
    LoadJsonStep,
    WriteJsonDirStep,
)

logger = logging.getLogger(__name__)

# Intermediate layer shared by the two preparation factories (clean/enrich):
# not expressed in PipelineLayerConfig (see the layer decision in SP05).
_CLEANED_LAYER = "cleaned"


def _article_id(article: CleanedArticleModel | EnrichedArticleModel) -> str:
    """Stable per-element id, derived from the element itself."""
    return element_id(article.source, article.number)


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
      `LoadJsonDirStep` → `ApplyStep` (chunk_articles, `FlatMap(ArticleChunker)`)
      → `EmbedChunksStep` → `ApplyStep` (map_to_chunk_entity) → `StoreChunksStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
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

    load_step = LoadJsonDirStep(
        "load_enriched_articles",
        indexing_config.input_layer,
        source,
        context_keys.ENRICHED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(
            EnrichedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    chunk_step = ApplyStep(
        "chunk_articles",
        FlatMap(ArticleChunker()),  # source now read from each article (Decision 17)
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
    force: bool = False,
    validate: bool = False,
) -> Flow:
    """Assembles the knowledge cleaning flow for ONE source (parsed → cleaned).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    No embed/store: this flow belongs to the preparation stage. `cleaned` is a
    per-element layer: one file per article, filtered by `FilterAlreadyDoneStep`
    (skipped entirely with `force=True`) before being written by `WriteJsonDirStep`.

    Step mapping:
      `LoadJsonStep` → `ApplyStep(clean + stamp source)` → `FilterAlreadyDoneStep`
      → `WriteJsonDirStep`

    The clean-then-stamp order matters (Decision 18): the filter needs `a.source`,
    which only exists after the parsed→cleaned map runs.

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
        source: Source to clean; must belong to `config.knowledge_preparation.sources`.
        force: If True, re-cleans every article even if already present in `cleaned/`.
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
    typed_source = cast(Literal["cds", "cap"], source)

    file_system_client = LocalFileSystemClient(config.project_root)

    load_step = LoadJsonStep(
        "load_parsed_articles",
        preparation_config.input_layer,
        source,
        context_keys.PARSED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(ParsedArticleModel, file_system_client=file_system_client),
    )

    # Clean first, then stamp the source: the filter needs `a.source` (Decision 18).
    clean_step = ApplyStep(
        "clean_articles",
        ForEach(ArticleCleaner()),
        ForEach(partial(ArticleMapper.from_parsed_to_cleaned, source=typed_source)),
        input_key=context_keys.PARSED_ARTICLES,
        output_key=context_keys.CLEANED_ARTICLES,
    )

    filter_step = FilterAlreadyDoneStep(
        "filter_cleaned",
        context_keys.CLEANED_ARTICLES,
        context_keys.FILTERED_ARTICLES,
        _CLEANED_LAYER,
        source,
        force,
        _article_id,
        layer_resolver,
        file_system_client,
    )

    write_step = WriteJsonDirStep(
        "write_cleaned",
        _CLEANED_LAYER,
        source,
        context_keys.FILTERED_ARTICLES,
        _article_id,
        layer_resolver,
        JsonRepository.get_instance(CleanedArticleModel, file_system_client=file_system_client),
    )

    flow: Flow = (
        FlowBuilder("knowledge_cleaning")
        .add_step(load_step)
        .add_step(clean_step)
        .add_step(filter_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow


def build_knowledge_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    open_router_provider: OpenRouterProvider,
    force: bool = False,
    validate: bool = False,
    tracker: LlmCallTracker | None = None,
) -> Flow:
    """Assembles the knowledge enrichment flow for ONE source (cleaned → enriched).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    No embed/store: this flow belongs to the preparation stage. Both `cleaned` and
    `enriched` are per-element layers: `FilterAlreadyDoneStep` runs *before* the LLM
    call (skipped entirely with `force=True`), since that call is the expensive
    transform this filter exists to save (Decision 18).

    Step mapping:
      `LoadJsonDirStep` → `FilterAlreadyDoneStep` → `ApplyStep(map_cleaned_articles)`
      → `AsyncApplyStep(enrich_articles)` → `WriteJsonDirStep`

    The enrichment phase runs under a single `asyncio.run` owned by `AsyncApplyStep`;
    per-article LLM calls fire concurrently, bounded by
    `config.article_contextualizer_concurrency` (symmetric to the quiz enrichment flow).

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
        source: Source to enrich; must belong to `config.knowledge_preparation.sources`.
        open_router_provider: OpenRouter provider injected into the enrichment agent.
        force: If True, re-enriches every article even if already present in `enriched/`.
        validate: If True, runs structural validation of the flow before returning it.
        tracker: Optional port persisting one `LlmCallLog` per call made by the
            enrichment agent. Forwarded to `from_yaml`; `None` disables tracking.

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

    file_system_client = LocalFileSystemClient(config.project_root)

    load_step = LoadJsonDirStep(
        "load_cleaned_articles",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(CleanedArticleModel, file_system_client=file_system_client),
    )

    # Filter BEFORE the expensive transform: this is what saves LLM calls.
    filter_step = FilterAlreadyDoneStep(
        "filter_enriched",
        context_keys.CLEANED_ARTICLES,
        context_keys.FILTERED_ARTICLES,
        preparation_config.output_layer,
        source,
        force,
        _article_id,
        layer_resolver,
        file_system_client,
    )

    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    agent = ArticleContextualizerAgent.from_yaml(
        "article_contextualizer", agents_repository, open_router_provider, tracker=tracker
    )
    # Base-map cleaned→enriched is a sync ApplyStep; the LLM enrichment is a separate
    # AsyncApplyStep that owns the single asyncio.run and fires per-article calls
    # concurrently (symmetric to the quiz enrichment flow).
    map_step = ApplyStep(
        "map_cleaned_articles",
        ForEach(ArticleMapper.from_cleaned_to_enriched),
        input_key=context_keys.FILTERED_ARTICLES,
        output_key=context_keys.MAPPED_ARTICLES,
    )
    enrich_step = AsyncApplyStep(
        "enrich_articles",
        ContextEnricher(config.article_contextualizer_concurrency, agent),
        input_key=context_keys.MAPPED_ARTICLES,
        output_key=context_keys.ENRICHED_ARTICLES,
    )

    write_step = WriteJsonDirStep(
        "write_enriched",
        preparation_config.output_layer,
        source,
        context_keys.ENRICHED_ARTICLES,
        _article_id,
        layer_resolver,
        JsonRepository.get_instance(EnrichedArticleModel, file_system_client=file_system_client),
    )

    flow: Flow = (
        FlowBuilder("knowledge_enrichment")
        .add_step(load_step)
        .add_step(filter_step)
        .add_step(map_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow
