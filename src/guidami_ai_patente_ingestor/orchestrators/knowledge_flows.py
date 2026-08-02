"""Factories for the knowledge preparation (SP05) and indexing (SP03) flows — per-source."""

import logging
from functools import partial
from typing import Literal, cast

from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep

from commons.ai.embedding import EmbeddingClient, EmbeddingService
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.observability import NullProgressReporter, ProgressReporter
from commons.repositories import JsonRepository
from commons.use_cases import FlatMap, ForEach
from commons.utils import element_id
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import CleanedArticleModel, ParsedArticleModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    EmbedCommasStep,
    StoreArticlesAndCommasStep,
)
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

from .progress_flow_observer import ProgressFlowObserver
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


def _article_id(article: CleanedArticleModel) -> str:
    """Stable per-element id, derived from the element itself."""
    return element_id(article.source, article.number)


def build_knowledge_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    source: str,
    validate: bool = False,
    progress: ProgressReporter | None = None,
) -> Flow:
    """Assembles the knowledge indexing flow for ONE source (corpus → map/expand → embed → store).

    The flow is per-source: it must run once per source (e.g. `cds`, then `cap`).
    The store performs a full-reload of that source only (delete-by-source + insert),
    so runs on different sources do not overwrite each other.

    Two independent derivations (PD-12) are computed from the same loaded
    `CleanedArticleModel` list rather than one being reconstructed from the other:
    article rows (`ARTICLE_ENTITIES`) and comma rows (`EMBEDDABLE_ARTICLE_COMMAS`).

    Step mapping:
      `LoadJsonDirStep` → `ApplyStep` (map_to_article_entities, `ForEach`)
      → `ApplyStep` (expand_to_embeddable_commas, `FlatMap`) → `EmbedCommasStep`
      → `StoreArticlesAndCommasStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
        embedding_client: Client for computing embeddings.
        postgres_client: Postgres client for DB operations.
        source: Source to index; must belong to `config.knowledge_indexing.sources`.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR; the benign WARNING on
            `EMBEDDABLE_ARTICLE_COMMAS` (EmbedCommasStep re-declares a key already
            produced by the expand_to_embeddable_commas step) does not block the build.
        progress: Optional reporter driving the step/flow bars (via a registered
            `ProgressFlowObserver`) and the embedding step's item bar. When `None`,
            defaults to `NullProgressReporter`, a no-op collaborator.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `source` is not among the valid sources configured for indexing.
    """
    indexing_config = config.knowledge_indexing
    reporter: ProgressReporter = progress if progress is not None else NullProgressReporter()

    valid_sources = set(indexing_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    load_step = LoadJsonDirStep(
        "load_cleaned_articles",
        indexing_config.input_layer,
        source,
        context_keys.CLEANED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(
            CleanedArticleModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    map_articles_step = ApplyStep(
        "map_to_article_entities",
        ForEach(ArticleMapper.from_cleaned_to_article_entity),
        input_key=context_keys.CLEANED_ARTICLES,
        output_key=context_keys.ARTICLE_ENTITIES,
    )

    expand_commas_step = ApplyStep(
        "expand_to_embeddable_commas",
        FlatMap(ArticleMapper.from_cleaned_to_embeddable_commas),
        input_key=context_keys.CLEANED_ARTICLES,
        output_key=context_keys.EMBEDDABLE_ARTICLE_COMMAS,
    )

    embed_step = EmbedCommasStep(
        "embed_commas",
        embed_repealed=config.embed_repealed,
        embedding_service=EmbeddingService(
            config.embedding_batch_size, embedding_client, reporter
        ),
    )

    store_step = StoreArticlesAndCommasStep(
        "store_articles_and_commas",
        source=source,
        article_repository=ArticleStoreRepository(config.articles_table, postgres_client),
        article_comma_repository=ArticleCommaStoreRepository(
            config.article_commas_table, postgres_client
        ),
    )

    flow: Flow = (
        FlowBuilder("knowledge_indexing")
        .add_step(load_step)
        .add_step(map_articles_step)
        .add_step(expand_commas_step)
        .add_step(embed_step)
        .add_step(store_step)
        .add_observer(ProgressFlowObserver(reporter))
        .build(validate=validate)
    )

    return flow


def build_knowledge_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    force: bool = False,
    validate: bool = False,
    progress: ProgressReporter | None = None,
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
        progress: Optional reporter driving the step/flow bars via a registered
            `ProgressFlowObserver`. When `None`, defaults to `NullProgressReporter`,
            a no-op collaborator. This flow has no instrumented service.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `source` is not among the valid sources configured for preparation.
    """
    preparation_config = config.knowledge_preparation
    reporter: ProgressReporter = progress if progress is not None else NullProgressReporter()

    valid_sources = set(preparation_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")
    typed_source = cast(Literal["cds", "cap", "reg"], source)

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
        .add_observer(ProgressFlowObserver(reporter))
        .build(validate=validate)
    )

    return flow
