"""Tests for build_quiz_cleaning_flow / build_quiz_enrichment_flow (SP09).

Replaces build_quiz_preparation_flow (removed): mirrors
build_knowledge_cleaning_flow / build_knowledge_enrichment_flow, but single-source
(no explicit `source` parameter: derived from `config.quiz_preparation.sources[0]`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from flowstep import Flow, FlowValidator
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.agents import NormReferenceDescriberAgent, RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberResponse,
)
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import RoadSignDescriberResponse
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_quiz_cleaning_flow,
    build_quiz_enrichment_flow,
)
from guidami_ai_patente_ingestor.services import LayerResolver

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter

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


_PROVIDER = OpenRouterProvider(api_key="test-key")


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
    """The chain is LoadParsedQuiz -> FlatMap+DeduplicateQuizItems -> WriteCleanedQuiz."""
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
            open_router_provider=_PROVIDER,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_name_is_quiz_enrichment() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            open_router_provider=_PROVIDER,
        )
    assert flow.name == "quiz_enrichment"


def test_enrichment_flow_required_input_keys_is_empty_set() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            open_router_provider=_PROVIDER,
        )
    report = FlowValidator().validate(flow)
    assert report.required_input_keys == set()


def test_enrichment_flow_build_with_validate_true_does_not_raise() -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            open_router_provider=_PROVIDER,
            validate=True,
        )
    assert isinstance(flow, Flow)


def test_enrichment_flow_has_four_steps_in_order() -> None:
    """The chain is LoadCleanedQuiz -> ApplyStep(map_cleaned_quiz) -> AsyncApplyStep(enrich_quiz).

    -> WriteEnrichedQuiz (single event loop, Decision 4).
    """
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer()):
        flow = build_quiz_enrichment_flow(
            config=_base_config(),
            layer_resolver=_make_layer_resolver(),
            open_router_provider=_PROVIDER,
        )
    steps = flow.get_steps()
    assert [step.name for step in steps] == [
        "load_cleaned_quiz",
        "map_cleaned_quiz",
        "enrich_quiz",
        "write_enriched_quiz",
    ]


# ---------------------------------------------------------------------------
# Progress reporting (T-10) — real filesystem, no real LLM calls, no real DB
# ---------------------------------------------------------------------------


def _quiz_resolver(tmp_path: Path, layers: dict[str, str]) -> LayerResolver:
    return LayerResolver(
        layers={name: str(tmp_path / name) for name in layers},
        sources={"quiz": SourceConfig(dir="quiz", file="quiz.json")},
    )


def _parsed_quiz_payload() -> dict:
    return {
        "question_id": 1,
        "topic": "Segnaletica",
        "sub_questions": [
            {"number": "1", "text": "Domanda di prova.", "correct_answer": True, "image": None}
        ],
    }


def test_cleaning_flow_reports_step_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    resolver = _quiz_resolver(tmp_path, {"parsed": "", "cleaned": ""})
    parsed_path = resolver.path("parsed", "quiz")
    parsed_path.parent.mkdir(parents=True)
    parsed_path.write_text(json.dumps([_parsed_quiz_payload()]), encoding="utf-8")

    config = IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        project_root=tmp_path,
    )

    build_quiz_cleaning_flow(
        config=config, layer_resolver=resolver, progress=progress_recorder
    ).run()

    begin_steps = [args for name, args in progress_recorder.calls if name == "begin_step"]
    end_steps = [args for name, args in progress_recorder.calls if name == "end_step"]
    assert len(begin_steps) == 3
    assert len(end_steps) == 3
    assert [args[1] for args in begin_steps] == [1, 2, 3]


def test_enrichment_flow_reports_step_and_item_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    resolver = _quiz_resolver(tmp_path, {"cleaned": "", "enriched": ""})
    cleaned_path = resolver.path("cleaned", "quiz")
    cleaned_path.parent.mkdir(parents=True)
    cleaned_path.write_text(
        json.dumps(
            [
                {
                    "question_id": 1,
                    "topic": "Segnaletica",
                    "number": "1",
                    "text": "Domanda di prova.",
                    "correct_answer": True,
                    "image": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    config = IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
        project_root=tmp_path,
    )

    describer = _patched_describer()
    describer.run.return_value = RoadSignDescriberResponse(
        visual_analysis="Analisi.", name="Stop", description="Segnale rosso."
    )
    norm_describer = MagicMock(spec=NormReferenceDescriberAgent)
    norm_describer.run.return_value = NormReferenceDescriberResponse(
        core_concepts=["concetto 1", "concetto 2"],
        exact_keywords=["parola 1", "parola 2", "parola 3"],
        vector_search_queries=["query 1", "query 2"],
        rule_explanation="Spiegazione breve.",
    )

    with (
        patch.object(RoadSignDescriberAgent, "from_yaml", return_value=describer),
        patch.object(NormReferenceDescriberAgent, "from_yaml", return_value=norm_describer),
    ):
        build_quiz_enrichment_flow(
            config=config,
            layer_resolver=resolver,
            open_router_provider=_PROVIDER,
            progress=progress_recorder,
        ).run()

    begin_steps = [args for name, args in progress_recorder.calls if name == "begin_step"]
    end_steps = [args for name, args in progress_recorder.calls if name == "end_step"]
    assert len(begin_steps) == 4
    assert len(end_steps) == 4
    assert [args[1] for args in begin_steps] == [1, 2, 3, 4]
    # Proves the reporter reached both injected quiz enrichers (no image -> 0 images).
    assert ("begin_items", ("images", 0)) in progress_recorder.calls
    assert ("begin_items", ("questions", 1)) in progress_recorder.calls
