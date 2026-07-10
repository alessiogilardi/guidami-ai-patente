"""Tests for build_knowledge_cleaning_flow / build_knowledge_enrichment_flow (SP05, per-source)."""

from unittest.mock import MagicMock, patch

import pytest
from flowstep import Flow, FlowValidator
from flowstep.steps import ApplyStep

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_cleaning_flow,
    build_knowledge_enrichment_flow,
)
from guidami_ai_patente_ingestor.orchestrators.steps.generic import (
    LoadJsonStep,
    WriteJsonStep,
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


# ---------------------------------------------------------------------------
# build_knowledge_cleaning_flow
# ---------------------------------------------------------------------------


def test_cleaning_flow_returns_flow_instance() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_required_input_keys_is_empty_set() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
    )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_cleaning_flow_build_with_validate_true_does_not_raise() -> None:
    flow = build_knowledge_cleaning_flow(
        config=_base_config(),
        layer_resolver=_make_layer_resolver(),
        source="cds",
        validate=True,
    )
    assert isinstance(flow, Flow)


def test_cleaning_flow_unknown_source_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        build_knowledge_cleaning_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="quiz",
        )


# ---------------------------------------------------------------------------
# build_knowledge_enrichment_flow
# ---------------------------------------------------------------------------


def _patched_agent() -> MagicMock:
    return MagicMock(spec=ArticleContextualizerAgent)


def test_enrichment_flow_returns_flow_instance() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_required_input_keys_is_empty_set() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
        )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_enrichment_flow_build_with_validate_true_does_not_raise() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
            validate=True,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_unknown_source_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="quiz",
        )


def test_enrichment_flow_has_three_steps_load_enrich_write() -> None:
    with patch.object(ArticleContextualizerAgent, "from_yaml", return_value=_patched_agent()):
        flow = build_knowledge_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            source="cds",
        )

    steps = flow.get_steps()
    assert len(steps) == 3
    assert isinstance(steps[0], LoadJsonStep)
    assert isinstance(steps[1], ApplyStep)
    assert isinstance(steps[2], WriteJsonStep)
