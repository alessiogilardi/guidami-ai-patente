"""Factory per i flow di quiz indexing (SP04) e quiz preparation (SP06, esteso da SP09)."""

import logging

from commons.clients import EmbeddingClient, PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.configs import AgentConfig
from commons.repositories import JsonRepository, YamlRepository
from commons.services.embeddings import EmbeddingService
from commons.use_cases import ForEach
from flowstep import Flow, FlowBuilder
from flowstep.steps import ApplyStep
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
from guidami_ai_patente_ingestor.services.quiz import EmbedQuizMetadata
from guidami_ai_patente_ingestor.services.quiz.enrichers import (
    ImageDescriptionEnricher,
    NormReferenceEnricher,
)
from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz
from guidami_ai_patente_ingestor.services.quiz.to_embeddable_quiz import ToEmbeddableQuiz

logger = logging.getLogger(__name__)

# Layer intermedio condiviso dalle due factory di preparation (clean/enrich):
# non espresso in PipelineLayerConfig (vedi decisione di layer in SP05, replicata da SP09).
_CLEANED_LAYER = "cleaned"


def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di quiz indexing (quiz bank → embeddable → embed → entity → store).

    Il quiz bank ha una sola source (`"quiz"`), derivata da
    `config.quiz_indexing.sources[0]`: lo store è un full-reload dell'intera
    `quiz_questions` (truncate + bulk_insert) tramite il `DbStoreStep` generico.

    Mappatura step:
      `LoadJsonStep` → `ApplyStep(map_to_embeddable)` → `ApplyStep(EmbedQuizMetadata)`
      → `ApplyStep(map_to_quiz_entity)` → `DbStoreStep`

    L'embedding è calcolato da `quiz_metadata.vector_search_queries`, non dal testo
    del quiz: gli item senza `quiz_metadata` transitano con `embedding = None`.

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        embedding_client: Client per il calcolo degli embedding.
        postgres_client: Client Postgres per le operazioni sul DB.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR.

    Returns:
        Flow configurato e pronto per l'esecuzione.
    """
    indexing_config = config.quiz_indexing
    source = indexing_config.sources[0]

    load_step = LoadJsonStep(
        "load_enriched_quiz",
        indexing_config.input_layer,
        source,
        context_keys.ENRICHED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(EnrichedQuizModel, LocalFileSystemClient(config.project_root)),
    )

    map_to_embeddable_step = ApplyStep(
        "map_to_embeddable",
        ToEmbeddableQuiz(),
        input_key=context_keys.ENRICHED_QUIZ,
        output_key=context_keys.EMBEDDABLE_QUIZ,
    )

    embed_step = ApplyStep(
        "embed_quiz",
        EmbedQuizMetadata(EmbeddingService(config.embedding_batch_size, embedding_client)),
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
    """Assembla il flow di quiz cleaning (parsed → cleaned, flatten+dedup).

    Nessun embed/store: questo flow appartiene allo stadio di preparazione. Il
    quiz bank ha una sola source (`"quiz"`), derivata da
    `config.quiz_preparation.sources[0]`.

    Mappatura step:
      `LoadJsonStep` → `ApplyStep(flatten_quiz)` → `WriteJsonStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR.

    Returns:
        Flow configurato e pronto per l'esecuzione.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]

    load_step = LoadJsonStep(
        "load_parsed_quiz",
        prep.input_layer,
        source,
        context_keys.PARSED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(ParsedQuizModel, LocalFileSystemClient(config.project_root)),
    )
    flatten_step = ApplyStep(
        "flatten_quiz",
        FlattenQuiz(),
        input_key=context_keys.PARSED_QUIZ,
        output_key=context_keys.CLEANED_QUIZ,
    )
    write_step = WriteJsonStep(
        "write_cleaned_quiz",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_QUIZ,
        layer_resolver,
        JsonRepository.get_instance(CleanedQuizModel, LocalFileSystemClient(config.project_root)),
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
) -> Flow:
    """Assembla il flow di quiz enrichment (cleaned → enriched).

    Stadio di preparazione: nessun embed/store. Il quiz bank ha una sola
    source (`"quiz"`), derivata da `config.quiz_preparation.sources[0]`.
    L'enrichment è Open/Closed: aggiungere un futuro enricher tocca solo la
    lista dei transform nell'ApplyStep, non lo step generico.

    Mappatura step:
      `LoadJsonStep` → `ApplyStep(enrich)` → `WriteJsonStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR.

    Returns:
        Flow configurato e pronto per l'esecuzione.

    Raises:
        ValueError: se `config.quiz_preparation.output_layer` non è configurato.
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
        JsonRepository.get_instance(CleanedQuizModel, LocalFileSystemClient(config.project_root)),
    )

    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    images_file_reader = LocalFileSystemClient(config.quiz_images_dir)
    describer = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_repository, images_file_reader
    )
    norm_describer = NormReferenceDescriberAgent.from_yaml(
        "norm_reference_describer", agents_repository
    )
    enrich_step = ApplyStep(
        "enrich",
        ForEach(QuizMapper.from_cleaned_to_enriched),
        ImageDescriptionEnricher(describer, images_file_reader),
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
        JsonRepository.get_instance(EnrichedQuizModel, LocalFileSystemClient(config.project_root)),
    )

    flow: Flow = (
        FlowBuilder("quiz_enrichment")
        .add_step(load_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .build(validate=validate)
    )

    return flow
