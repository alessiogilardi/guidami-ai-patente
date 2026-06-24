"""Test per build_quiz_preparation_flow (SP06, single-source, no embed/store)."""

from unittest.mock import MagicMock

from commons.configs import PostgresConnectionConfig
from commons.flowstep import Flow, FlowValidator
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import build_quiz_preparation_flow
from guidami_ai_patente_ingestor.services import LayerResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_config() -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def _make_layer_resolver() -> LayerResolver:
    return MagicMock(spec=LayerResolver)


def _build(validate: bool = False) -> Flow:
    return build_quiz_preparation_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        validate=validate,
    )


# ---------------------------------------------------------------------------
# Unit tests — no filesystem, no DB
# ---------------------------------------------------------------------------


def test_build_returns_flow_instance() -> None:
    assert isinstance(_build(), Flow)


def test_flow_name_is_quiz_preparation() -> None:
    assert _build().name == "quiz_preparation"


def test_flow_required_input_keys_is_empty_set() -> None:
    """Il flow non richiede chiavi esterne: LoadJsonStep parte da zero."""
    report = FlowValidator().validate(_build())
    assert report.required_input_keys == set()


def test_build_with_validate_true_does_not_raise() -> None:
    assert isinstance(_build(validate=True), Flow)


def test_flow_has_three_steps_in_order() -> None:
    """La catena è LoadQuiz → EnrichQuiz → WriteEnrichedQuiz."""
    steps = _build().get_steps()
    assert [step.name for step in steps] == [
        "load_quiz",
        "enrich_quiz",
        "write_enriched_quiz",
    ]
