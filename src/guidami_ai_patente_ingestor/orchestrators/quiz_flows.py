"""Factories for the quiz indexing (SP04) and quiz preparation (SP06, extended by SP09) flows."""

from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep

from commons.ai.agents import AgentConfig
from commons.ai.embedding import EmbeddingClient, EmbeddingService
from commons.ai.observability import LlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import JsonRepository, YamlRepository
from commons.use_cases import FlatMap, ForEach
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
    DbStoreStep,
    LoadJsonStep,
    WriteJsonStep,
)
from guidami_ai_patente_ingestor.repositories import QuizQuestionStoreRepository
from guidami_ai_patente_ingestor.services import LayerResolver
from guidami_ai_patente_ingestor.services.quiz import DeduplicateQuizItems, EmbedQuizMetadata
from guidami_ai_patente_ingestor.services.quiz.enrichers import (
    ImageDescriptionEnricher,
    NormReferenceEnricher,
)

# Intermediate layer shared by the two preparation factories (clean/enrich):
# not expressed in PipelineLayerConfig (see the layer decision in SP05, replicated by SP09).
_CLEANED_LAYER = "cleaned"


def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow:
    """Assembles the quiz indexing flow (quiz bank → embeddable → embed → entity → store).

    The quiz bank has a single source (`"quiz"`), derived from
    `config.quiz_indexing.sources[0]`: the store is a full-reload of the entire
    `quiz_questions` table (truncate + bulk_insert) via the generic `DbStoreStep`.

    Step mapping:
      `LoadJsonStep` → `ApplyStep(DeduplicateQuizItems, map_to_embeddable)`
      → `ApplyStep(EmbedQuizMetadata)` → `ApplyStep(map_to_quiz_entity)` → `DbStoreStep`

    The `map_to_embeddable` step chains two transforms: dedup on the triple
    (normalized text, correct answer, image identity) via
    `DeduplicateQuizItems` (shared with `build_quiz_cleaning_flow`), then a
    1:1 enriched→embeddable mapping via `ForEach(QuizMapper.from_enriched_to_embeddable)`.

    The embedding is computed from `quiz_metadata.vector_search_queries`, not from
    the quiz text: items without `quiz_metadata` pass through with `embedding = None`.

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        embedding_client: Client for computing embeddings.
        postgres_client: Postgres client for DB operations.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.

    Returns:
        Flow configured and ready for execution.
    """
    indexing_config = config.quiz_indexing
    source = indexing_config.sources[0]

    load_step = LoadJsonStep(
        "load_enriched_quiz",
        indexing_config.input_layer,
        source,
        context_keys.ENRICHED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            EnrichedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    map_to_embeddable_step = ApplyStep(
        "map_to_embeddable",
        DeduplicateQuizItems(),
        ForEach(QuizMapper.from_enriched_to_embeddable),
        input_key=context_keys.ENRICHED_QUIZ,
        output_key=context_keys.EMBEDDABLE_QUIZ,
    )

    embed_step = ApplyStep(
        "embed_quiz",
        EmbedQuizMetadata(
            embedding_service=EmbeddingService(config.embedding_batch_size, embedding_client)
        ),
        input_key=context_keys.EMBEDDABLE_QUIZ,
        output_key=context_keys.EMBEDDABLE_QUIZ,
    )

    map_to_quiz_entity_step = ApplyStep(
        "map_to_quiz_entity",
        ForEach(QuizMapper.from_embeddable_to_quiz_question),
        input_key=context_keys.EMBEDDABLE_QUIZ,
        output_key=context_keys.QUIZ_ENTITIES,
    )

    store_step = DbStoreStep(
        "store_quiz",
        context_keys.QUIZ_ENTITIES,
        QuizQuestionStoreRepository(config.quiz_questions_table, postgres_client),
    )

    flow: Flow = (
        FlowBuilder("quiz_indexing")
        .add_step(load_step)
        .add_step(map_to_embeddable_step)
        .add_step(embed_step)
        .add_step(map_to_quiz_entity_step)
        .add_step(store_step)
        .build(validate=validate)
    )

    return flow


def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow:
    """Assembles the quiz cleaning flow (parsed → cleaned, flatten + dedup).

    No embed/store: this flow belongs to the preparation stage. The quiz bank
    has a single source (`"quiz"`), derived from
    `config.quiz_preparation.sources[0]`.

    Step mapping:
      `LoadJsonStep`
      → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems)`
      → `WriteJsonStep`

    The `flatten_quiz` step chains two transforms: unnest+map parsed→cleaned via
    `FlatMap(QuizMapper.from_parsed_to_cleaned_all)`, then dedup on the triple
    (normalized text, correct answer, image identity) via
    `DeduplicateQuizItems` (shared with `build_quiz_indexing_flow`).

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.

    Returns:
        Flow configured and ready for execution.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]

    load_step = LoadJsonStep(
        "load_parsed_quiz",
        prep.input_layer,
        source,
        context_keys.PARSED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            ParsedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )
    flatten_step = ApplyStep(
        "flatten_quiz",
        FlatMap(QuizMapper.from_parsed_to_cleaned_all),
        DeduplicateQuizItems(),
        input_key=context_keys.PARSED_QUIZ,
        output_key=context_keys.CLEANED_QUIZ,
    )
    write_step = WriteJsonStep(
        "write_cleaned_quiz",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            CleanedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    flow: Flow = (
        FlowBuilder("quiz_cleaning")
        .add_step(load_step)
        .add_step(flatten_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow


def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
    tracker: LlmCallTracker | None = None,
) -> Flow:
    """Assembles the quiz enrichment flow (cleaned → enriched).

    Preparation stage: no embed/store. The quiz bank has a single source
    (`"quiz"`), derived from `config.quiz_preparation.sources[0]`.
    The enrichment is Open/Closed: adding a future enricher only touches the
    list of transforms in the ApplyStep, not the generic step.

    Step mapping:
      `LoadJsonStep` → `ApplyStep(enrich)` → `WriteJsonStep`

    Args:
        config: Full ingestor configuration (already loaded at the entry point).
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        validate: If True, runs structural validation of the flow before returning it.
            Raises `FlowValidationError` on ERROR.
        tracker: Optional port persisting one `LlmCallLog` per call made by the
            enrichment agents. Forwarded to `from_yaml`; `None` disables tracking.

    Returns:
        Flow configured and ready for execution.

    Raises:
        ValueError: if `config.quiz_preparation.output_layer` is not configured.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]

    if prep.output_layer is None:
        raise ValueError("quiz_preparation.output_layer is not configured")

    load_step = LoadJsonStep(
        "load_cleaned_quiz",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            CleanedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    images_file_reader = LocalFileSystemClient(config.quiz_images_dir)
    describer = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_repository, images_file_reader, tracker
    )
    norm_describer = NormReferenceDescriberAgent.from_yaml(
        "norm_reference_describer", agents_repository, tracker=tracker
    )
    enrich_step = ApplyStep(
        "enrich",
        ForEach(QuizMapper.from_cleaned_to_enriched),
        ImageDescriptionEnricher(describer),
        NormReferenceEnricher(norm_describer),
        input_key=context_keys.CLEANED_QUIZ,
        output_key=context_keys.ENRICHED_QUIZ,
    )

    write_step = WriteJsonStep(
        "write_enriched_quiz",
        prep.output_layer,
        source,
        context_keys.ENRICHED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(
            EnrichedQuizModel, file_system_client=LocalFileSystemClient(config.project_root)
        ),
    )

    flow: Flow = (
        FlowBuilder("quiz_enrichment")
        .add_step(load_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow
