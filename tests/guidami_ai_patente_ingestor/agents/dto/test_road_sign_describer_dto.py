"""Tests for RoadSignDescriberRequest and RoadSignDescriberResponse DTOs."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    QuizContextModel,
    RoadSignDescriberRequest,
)


def test_request_accepts_a_list_of_quiz_contexts() -> None:
    request = RoadSignDescriberRequest(
        contexts=[
            QuizContextModel(topic="A", texts=["uno"]),
            QuizContextModel(topic="B", texts=["due"]),
        ]
    )
    assert request.contexts == [
        QuizContextModel(topic="A", texts=["uno"]),
        QuizContextModel(topic="B", texts=["due"]),
    ]


def test_request_contexts_block_renders_topic_and_dot_list_of_questions() -> None:
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="Segnaletica", texts=["a", "b"])]
    )
    assert request.contexts_block == "Argomento: Segnaletica\nDomande:\n- a\n- b"


def test_request_contexts_block_joins_multiple_topics_with_blank_line() -> None:
    request = RoadSignDescriberRequest(
        contexts=[
            QuizContextModel(topic="A", texts=["uno"]),
            QuizContextModel(topic="B", texts=["due"]),
        ]
    )
    assert request.contexts_block == (
        "Argomento: A\nDomande:\n- uno\n\nArgomento: B\nDomande:\n- due"
    )


def test_request_contexts_block_is_exposed_in_model_dump() -> None:
    request = RoadSignDescriberRequest(contexts=[QuizContextModel(topic="A", texts=["a"])])
    assert "contexts_block" in request.model_dump()


def test_response_fields_are_ordered_visual_analysis_name_description() -> None:
    from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
        RoadSignDescriberResponse,
    )

    fields = list(RoadSignDescriberResponse.model_fields.keys())
    assert fields == ["visual_analysis", "name", "description"], (
        f"Expected CoT field order [visual_analysis, name, description], got {fields}"
    )


def test_response_visual_analysis_field_is_required() -> None:
    from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
        RoadSignDescriberResponse,
    )

    with pytest.raises(ValidationError):
        RoadSignDescriberResponse(name="Stop", description="Segnale rosso.")  # type: ignore[call-arg]


def test_response_accepts_visual_analysis_value() -> None:
    from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
        RoadSignDescriberResponse,
    )

    resp = RoadSignDescriberResponse(
        visual_analysis="Segnale ottagonale rosso con scritta STOP.",
        name="Stop",
        description="Segnale di arresto obbligatorio.",
    )
    assert resp.visual_analysis == "Segnale ottagonale rosso con scritta STOP."
