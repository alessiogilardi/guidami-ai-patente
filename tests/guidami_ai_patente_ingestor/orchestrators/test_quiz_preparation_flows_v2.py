"""Test per build_quiz_cleaning_flow / build_quiz_enrichment_flow (SP09).

Rimpiazzano build_quiz_preparation_flow (rimosso): mirror di
build_knowledge_cleaning_flow / build_knowledge_enrichment_flow, ma single-source
(niente parametro `source` esplicito: deriva da `config.quiz_preparation.sources[0]`).
"""

from unittest.mock import MagicMock, patch

from commons.configs import PostgresConnectionConfig
from flowstep import Flow, FlowValidator
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_quiz_cleaning_flow,
    build_quiz_enrichment_flow,
)
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


def _patched_describer() -> MagicMock:
    return MagicMock(spec=RoadSignDescriberAgent)


# ---------------------------------------------------------------------------
# build_quiz_cleaning_flow
# ---------------------------------------------------------------------------


def test_cleaning_flow_returns_flow_instance() -> None:
    flow = build_quiz_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_name_is_quiz_cleaning() -> None:
    flow = build_quiz_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
    )
    assert flow.name == "quiz_cleaning"


def test_cleaning_flow_required_input_keys_is_empty_set() -> None:
    flow = build_quiz_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
    )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_cleaning_flow_build_with_validate_true_does_not_raise() -> None:
    flow = build_quiz_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        validate=True,
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_has_three_steps_in_order() -> None:
    """La catena è LoadParsedQuiz -> FlatMap+DeduplicateQuizItems -> WriteCleanedQuiz."""
    flow = build_quiz_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
    )
    steps = flow.get_steps()
    assert [step.name for step in steps] == [
        "load_parsed_quiz",
        "flatten_quiz",
        "write_cleaned_quiz",
    ]


# ---------------------------------------------------------------------------
# build_quiz_enrichment_flow
# ---------------------------------------------------------------------------


def test_enrichment_flow_returns_flow_instance() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_name_is_quiz_enrichment() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
        )
    assert flow.name == "quiz_enrichment"


def test_enrichment_flow_required_input_keys_is_empty_set() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
        )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_enrichment_flow_build_with_validate_true_does_not_raise() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            validate=True,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_has_three_steps_in_order() -> None:
    """La catena è LoadCleanedQuiz -> Enrich -> WriteEnrichedQuiz."""
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
        )
    steps = flow.get_steps()
    assert [step.name for step in steps] == [
        "load_cleaned_quiz",
        "enrich",
        "write_enriched_quiz",
    ]
