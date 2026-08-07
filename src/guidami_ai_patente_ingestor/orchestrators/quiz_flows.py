"""Factories for the quiz indexing (SP04) and quiz preparation (SP06, extended by SP09) flows."""

from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep, AsyncApplyStep
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.embedding import EmbeddingClient, EmbeddingService
from commons.ai.observability import LlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.observability import NullProgressReporter, ProgressReporter
from commons.repositories import JsonRepository, YamlRepository
from commons.use_cases import FlatMap, ForEach
from commons.utils import element_id
from guidami_ai_patente_ingestor.agents import NormReferenceDescriberAgent, RoadSignDescriberAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    EnrichedQuizModel,
    ParsedQuizModel,
)
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.generic import (
    FilterAlreadyDoneStep,
    LoadJsonDirStep,
    LoadJsonStep,
    WriteJsonDirStep,
)
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import StoreQuizStep
from guidami_ai_patente_ingestor.providers import LayerResolverProvider
from guidami_ai_patente_ingestor.repositories import (
    QuizImageStoreRepository,
    QuizQuestionEmbeddingStoreRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services.quiz import (
    DeduplicateQuizItemsService,
    EmbedQuizVariantsService,
)
from guidami_ai_patente_ingestor.services.quiz.enrichers import (
    ImageDescriptionEnricherService,
    NormReferenceEnricherService,
)

from .progress_flow_observer import ProgressFlowObserver

# Intermediate layer shared by the two preparation factories (clean/enrich):
# not expressed in PipelineLayerConfig (see the layer decision in SP05, replicated by SP09).
_CLEANED_LAYER = "cleaned"


def _quiz_id(item: CleanedQuizModel | EnrichedQuizModel) -> str:
    """Stable per-element id, derived from the item's own natural key."""
    return element_id("quiz", item.number)


def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolverProvider,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
    progress: ProgressReporter | None = None,
) -> Flow:
    """Assembles the quiz indexing flow (quiz bank → embedded → variants → entity → store).

    The quiz bank has a single source (`"quiz"`), derived from
    `config.quiz_indexing.sources[0]`: the store upserts `quiz_questions`,
    `quiz_question_embeddings`, and `quiz_images`, and reconciles `quiz_questions`
    against this run's input via the domain-specific `StoreQuizStep`.

    Step mapping:
      `LoadJsonDirStep` → `ApplyStep(map_to_embedded)` → `ApplyStep(embed_quiz_variants)`
      → `ApplyStep(map_to_quiz_entity)` → `ApplyStep(map_to_quiz_images)` → `StoreQuizStep`

    The `map_to_embedded` step chains two transforms: dedup on the triple
    (normalized text, correct answer, image identity) via
    `DeduplicateQuizItemsService` (shared with `build_quiz_cleaning_flow`), then a
    1:1 enriched→embedded mapping via `ForEach(QuizMapper.from_enriched_to_embedded)`.

    The `embed_quiz_variants` step computes and embeds every configured query
    representation (AD-7) for every item — one embedding-service call per variant, not
    per question — producing `EmbeddableQuizVariant` rows plus per-variant omission
    counts (`EmbedQuizVariantsResult`), later written by `StoreQuizStep`.

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        embedding_client: Client for computing embeddings.
        postgres_client: Postgres client for DB operations.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.
        progress: Optional reporter driving the step/flow bars (via a registered
            `ProgressFlowObserver`) and, through `EmbedQuizVariantsService`, the embedding
            step's item bar. When `None`, defaults to `NullProgressReporter`, a no-op
            collaborator.

    Returns:
        Flow configured and ready for execution.
    """
    indexing_config = config.quiz_indexing
    source = indexing_config.sources[0]
    reporter: ProgressReporter = progress if progress is not None else NullProgressReporter()

    load_step = LoadJsonDirStep(
        "load_enriched_quiz",
        indexing_config.input_layer,
        source,
        context_keys.ENRICHED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            EnrichedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    map_to_embedded_step = ApplyStep(
        "map_to_embedded",
        DeduplicateQuizItemsService(),
        ForEach(QuizMapper.from_enriched_to_embedded),
        input_key=context_keys.ENRICHED_QUIZ,
        output_key=context_keys.EMBEDDED_QUIZ,
    )

    embed_variants_step = ApplyStep(
        "embed_quiz_variants",
        EmbedQuizVariantsService(
            config.quiz_embedding_variants,
            EmbeddingService(config.embedding_batch_size, embedding_client, reporter),
        ),
        input_key=context_keys.EMBEDDED_QUIZ,
        output_key=context_keys.QUIZ_VARIANT_EMBEDDINGS,
    )

    map_to_quiz_entity_step = ApplyStep(
        "map_to_quiz_entity",
        ForEach(QuizMapper.from_embedded_to_quiz_question),
        input_key=context_keys.EMBEDDED_QUIZ,
        output_key=context_keys.QUIZ_ENTITIES,
    )

    map_to_quiz_images_step = ApplyStep(
        "map_to_quiz_images",
        FlatMap(QuizMapper.from_embedded_to_quiz_images),
        input_key=context_keys.EMBEDDED_QUIZ,
        output_key=context_keys.QUIZ_IMAGE_ENTITIES,
    )

    store_step = StoreQuizStep(
        "store_quiz",
        QuizQuestionStoreRepository(config.quiz_questions_table, postgres_client),
        QuizImageStoreRepository(config.quiz_images_table, postgres_client),
        QuizQuestionEmbeddingStoreRepository(
            config.quiz_question_embeddings_table, postgres_client
        ),
    )

    flow: Flow = (
        FlowBuilder("quiz_indexing")
        .add_step(load_step)
        .add_step(map_to_embedded_step)
        .add_step(embed_variants_step)
        .add_step(map_to_quiz_entity_step)
        .add_step(map_to_quiz_images_step)
        .add_step(store_step)
        .add_observer(ProgressFlowObserver(reporter))
        .build(validate=validate)
    )

    return flow


def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolverProvider,
    force: bool = False,
    validate: bool = False,
    progress: ProgressReporter | None = None,
) -> Flow:
    """Assembles the quiz cleaning flow (parsed → cleaned, flatten + dedup).

    No embed/store: this flow belongs to the preparation stage. The quiz bank
    has a single source (`"quiz"`), derived from
    `config.quiz_preparation.sources[0]`. `cleaned` is a per-element layer: one
    file per cleaned item, filtered by `FilterAlreadyDoneStep` (skipped entirely
    with `force=True`) before being written by `WriteJsonDirStep`.

    Step mapping:
      `LoadJsonStep` → `ApplyStep(FlatMap(...), DeduplicateQuizItemsService)` →
      `FilterAlreadyDoneStep` → `WriteJsonDirStep`

    The `flatten_quiz` step chains two transforms: unnest+map parsed→cleaned via
    `FlatMap(QuizMapper.from_parsed_to_cleaned_all)`, then dedup on the triple
    (normalized text, correct answer, image identity) via
    `DeduplicateQuizItemsService` (shared with `build_quiz_indexing_flow`).

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
        force: If True, re-cleans every item even if already present in `cleaned/`.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.
        progress: Optional reporter driving the step/flow bars via a registered
            `ProgressFlowObserver`. When `None`, defaults to `NullProgressReporter`,
            a no-op collaborator. This flow has no instrumented service.

    Returns:
        Flow configured and ready for execution.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]
    reporter: ProgressReporter = progress if progress is not None else NullProgressReporter()
    file_system_client = LocalFileSystemClient(config.project_root)

    load_step = LoadJsonStep(
        "load_parsed_quiz",
        prep.input_layer,
        source,
        context_keys.PARSED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(ParsedQuizModel, file_system_client=file_system_client),
    )
    flatten_step = ApplyStep(
        "flatten_quiz",
        FlatMap(QuizMapper.from_parsed_to_cleaned_all),
        DeduplicateQuizItemsService(),
        input_key=context_keys.PARSED_QUIZ,
        output_key=context_keys.CLEANED_QUIZ,
    )
    filter_step = FilterAlreadyDoneStep(
        "filter_cleaned_quiz",
        context_keys.CLEANED_QUIZ,
        context_keys.FILTERED_QUIZ,
        _CLEANED_LAYER,
        source,
        force,
        _quiz_id,
        layer_resolver,
        file_system_client,
    )
    write_step = WriteJsonDirStep(
        "write_cleaned_quiz",
        _CLEANED_LAYER,
        source,
        context_keys.FILTERED_QUIZ,
        _quiz_id,
        layer_resolver,
        JsonRepository.get_instance(CleanedQuizModel, file_system_client=file_system_client),
    )

    flow: Flow = (
        FlowBuilder("quiz_cleaning")
        .add_step(load_step)
        .add_step(flatten_step)
        .add_step(filter_step)
        .add_step(write_step)
        .add_observer(ProgressFlowObserver(reporter))
        .build(validate=validate)
    )

    return flow


def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolverProvider,
    open_router_provider: OpenRouterProvider,
    force: bool = False,
    validate: bool = False,
    tracker: LlmCallTracker | None = None,
    progress: ProgressReporter | None = None,
) -> Flow:
    """Assembles the quiz enrichment flow (cleaned → enriched).

    Preparation stage: no embed/store. The quiz bank has a single source
    (`"quiz"`), derived from `config.quiz_preparation.sources[0]`. `enriched` is
    a per-element layer: one file per enriched item, filtered by
    `FilterAlreadyDoneStep` (skipped entirely with `force=True`) *before* the
    expensive LLM transform, then written by `WriteJsonDirStep`.
    The enrichment is Open/Closed: adding a future async enricher only touches the
    list of transforms in the `AsyncApplyStep`, not the generic step.

    Step mapping:
      `LoadJsonDirStep` → `FilterAlreadyDoneStep` → `ApplyStep(map_cleaned_quiz)`
      → `AsyncApplyStep(enrich_quiz)` → `WriteJsonDirStep`

    The whole enrichment phase (`AsyncApplyStep(enrich_quiz)`) runs under a single
    `asyncio.run`: image description enrichment always completes before norm reference
    enrichment starts (sequential awaits), so no client held by the enrichment agents is
    ever reused across event loops.

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → container directory.
        open_router_provider: OpenRouter provider injected into the enrichment agents.
        force: If True, re-enriches every item even if already present in `enriched/`.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.
        tracker: Optional port persisting one `LlmCallLogEntity` per call made by the
            enrichment agents. Forwarded to `from_yaml`; `None` disables tracking.
        progress: Optional reporter driving the step/flow bars (via a registered
            `ProgressFlowObserver`) and, in sequence, the image-description and
            norm-reference enrichers' item bars. When `None`, defaults to
            `NullProgressReporter`, a no-op collaborator.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `config.quiz_preparation.output_layer` is not configured.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]
    reporter: ProgressReporter = progress if progress is not None else NullProgressReporter()

    if prep.output_layer is None:
        raise ValueError("quiz_preparation.output_layer is not configured")

    file_system_client = LocalFileSystemClient(config.project_root)

    load_step = LoadJsonDirStep(
        "load_cleaned_quiz",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(CleanedQuizModel, file_system_client=file_system_client),
    )

    filter_step = FilterAlreadyDoneStep(
        "filter_enriched_quiz",
        context_keys.CLEANED_QUIZ,
        context_keys.FILTERED_QUIZ,
        prep.output_layer,
        source,
        force,
        _quiz_id,
        layer_resolver,
        file_system_client,
    )

    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    images_file_reader = LocalFileSystemClient(config.quiz_images_dir)
    describer = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer",
        agents_repository,
        open_router_provider,
        images_file_reader,
        tracker,
    )
    norm_describer = NormReferenceDescriberAgent.from_yaml(
        "norm_reference_describer", agents_repository, open_router_provider, tracker=tracker
    )
    map_step = ApplyStep(
        "map_cleaned_quiz",
        ForEach(QuizMapper.from_cleaned_to_enriched),
        input_key=context_keys.FILTERED_QUIZ,
        output_key=context_keys.MAPPED_QUIZ,
    )
    enrich_step = AsyncApplyStep(
        "enrich_quiz",
        ImageDescriptionEnricherService(
            config.road_sign_describer_concurrency, describer, reporter
        ),
        NormReferenceEnricherService(
            config.norm_reference_describer_concurrency, norm_describer, reporter
        ),
        input_key=context_keys.MAPPED_QUIZ,
        output_key=context_keys.ENRICHED_QUIZ,
    )

    write_step = WriteJsonDirStep(
        "write_enriched_quiz",
        prep.output_layer,
        source,
        context_keys.ENRICHED_QUIZ,
        _quiz_id,
        layer_resolver,
        JsonRepository.get_instance(EnrichedQuizModel, file_system_client=file_system_client),
    )

    flow: Flow = (
        FlowBuilder("quiz_enrichment")
        .add_step(load_step)
        .add_step(filter_step)
        .add_step(map_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .add_observer(ProgressFlowObserver(reporter))
        .build(validate=validate)
    )

    return flow
