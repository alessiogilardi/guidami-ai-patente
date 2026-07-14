"""Tests for build_quiz_indexing_flow (flow factory SP04, single-source full-reload)."""

from unittest.mock import MagicMock

from flowstep import Flow, FlowValidator

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import build_quiz_indexing_flow
from guidami_ai_patente_ingestor.services import LayerResolver

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _base_config() -> IngestorConfig:
    return IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def _make_embedding_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    client.embed_passages.side_effect = lambda texts: [[float(len(t))] * 1536 for t in texts]
    return client


def _make_postgres_client() -> PostgresClient:
    return MagicMock(spec=PostgresClient)


def _build(validate: bool = False) -> Flow:
    return build_quiz_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        validate=validate,
    )


# ---------------------------------------------------------------------------
# Unit tests — no filesystem, no DB
# ---------------------------------------------------------------------------


def test_build_returns_flow_instance() -> None:
    assert isinstance(_build(), Flow)


def test_flow_name_is_quiz_indexing() -> None:
    assert _build().name == "quiz_indexing"


def test_flow_required_input_keys_is_empty_set() -> None:
    """The flow requires no external keys: LoadJsonStep starts from scratch."""
    report = FlowValidator().validate(_build())
    assert report.required_input_keys == set()


def test_build_with_validate_true_does_not_raise() -> None:
    """validate=True does not raise (the WARNING on EMBEDDABLE_QUIZ is benign)."""
    assert isinstance(_build(validate=True), Flow)


def test_flow_has_five_steps_in_order() -> None:
    """The chain is Load → MapToEmbeddable → Embed → MapToQuizEntity → Store."""
    steps = _build().get_steps()
    assert [step.name for step in steps] == [
        "load_enriched_quiz",
        "map_to_embeddable",
        "embed_quiz",
        "map_to_quiz_entity",
        "store_quiz",
    ]
