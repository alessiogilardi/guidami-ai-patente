"""Factory per i flow di quiz indexing (SP04) e quiz preparation (SP06)."""

import logging

from commons.clients import EmbeddingClient, PostgresClient
from commons.flowstep import Flow, FlowBuilder
from commons.services.embeddings import EmbeddingService
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.generic import DbStoreStep, EmbedStep
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import (
    EnrichQuizStep,
    LoadEnrichedQuizStep,
    LoadQuizStep,
    MapToEmbeddableStep,
    MapToQuizEntityStep,
    WriteEnrichedQuizStep,
)
from guidami_ai_patente_ingestor.repositories import (
    EnrichedQuizBankRepository,
    QuizBankRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver, QuizEnrichmentService
from guidami_ai_patente_ingestor.services.quiz.enrichers import (
    ImageDescriptionEnricher,
    QuizEnricher,
)

logger = logging.getLogger(__name__)


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
      `LoadEnrichedQuizStep` → `MapToEmbeddableStep` → `EmbedStep`
      → `MapToQuizEntityStep` → `DbStoreStep`

    Args:
        config: Configurazione completa dell'ingestor (già caricata all'entry point).
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        embedding_client: Client per il calcolo degli embedding.
        postgres_client: Client Postgres per le operazioni sul DB.
        validate: Se True, esegue la validazione strutturale del flow prima di restituirlo.
            Solleva `FlowValidationError` su ERROR; il WARNING benigno su
            `EMBEDDABLE_QUIZ` (l'`EmbedStep` ri-dichiara una chiave già prodotta da
            `MapToEmbeddableStep`) non blocca la build.

    Returns:
        Flow configurato e pronto per l'esecuzione.
    """
    indexing_config = config.quiz_indexing
    source = indexing_config.sources[0]

    load_step = LoadEnrichedQuizStep(
        "load_enriched_quiz",
        EnrichedQuizBankRepository(),
        layer_resolver,
        indexing_config.input_layer,
        source,
    )

    map_to_embeddable_step = MapToEmbeddableStep("map_to_embeddable")

    embed_step = EmbedStep(
        "embed_quiz",
        EmbeddingService(embedding_client, config.embedding_batch_size),
        context_keys.EMBEDDABLE_QUIZ,
    )

    map_to_quiz_entity_step = MapToQuizEntityStep("map_to_quiz_entity")

    store_step = DbStoreStep(
        "store_quiz",
        QuizQuestionStoreRepository(postgres_client, config.quiz_questions_table),
        context_keys.QUIZ_ENTITIES,
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


def build_quiz_preparation_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di quiz preparation (quiz bank cleaned → enriched).

    Stadio di preparazione: nessun embed/store. Il quiz bank ha una sola
    source (`"quiz"`), derivata da `config.quiz_preparation.sources[0]`.
    L'enrichment è Open/Closed: aggiungere un futuro enricher tocca solo la
    lista `enrichers` qui sotto, non lo step né il service.

    Mappatura step:
      `LoadQuizStep` → `EnrichQuizStep` → `WriteEnrichedQuizStep`

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

    describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", config.agents_dir)
    enrichers: list[QuizEnricher] = [ImageDescriptionEnricher(describer, config.quiz_images_dir)]
    enrichment_service = QuizEnrichmentService(enrichers)

    flow: Flow = (
        FlowBuilder("quiz_preparation")
        .add_step(
            LoadQuizStep(
                "load_quiz", QuizBankRepository(), layer_resolver, prep.input_layer, source
            )
        )
        .add_step(EnrichQuizStep("enrich_quiz", enrichment_service))
        .add_step(
            WriteEnrichedQuizStep(
                "write_enriched_quiz",
                EnrichedQuizBankRepository(),
                layer_resolver,
                prep.output_layer,
                source,
            )
        )
        .build(validate=validate)
    )

    return flow
