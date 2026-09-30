"""Tests for RoadSignDescriberRequest and RoadSignDescriberResponse DTOs."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    QuizContextModel,
    QuizStatementModel,
    RoadSignDescriberRequest,
)


def _statement(text: str, correct_answer: bool = True) -> QuizStatementModel:
    return QuizStatementModel(text=text, correct_answer=correct_answer)


def test_request_accepts_a_list_of_quiz_contexts() -> None:
    request = RoadSignDescriberRequest(
        contexts=[
            QuizContextModel(topic="A", statements=[_statement("uno")]),
            QuizContextModel(topic="B", statements=[_statement("due")]),
        ]
    )
    assert [c.topic for c in request.contexts] == ["A", "B"]
    assert request.contexts[0].statements == [_statement("uno")]


def test_request_contexts_block_renders_answer_label_before_each_statement() -> None:
    request = RoadSignDescriberRequest(
        contexts=[
            QuizContextModel(
                topic="Segnaletica",
                statements=[_statement("a", True), _statement("b", False)],
            )
        ]
    )
    assert request.contexts_block == ("Argomento: Segnaletica\nDomande:\n- (Vero) a\n- (Falso) b")


def test_request_contexts_block_joins_multiple_topics_with_blank_line() -> None:
    request = RoadSignDescriberRequest(
        contexts=[
            QuizContextModel(topic="A", statements=[_statement("uno")]),
            QuizContextModel(topic="B", statements=[_statement("due", False)]),
        ]
    )
    assert request.contexts_block == (
        "Argomento: A\nDomande:\n- (Vero) uno\n\nArgomento: B\nDomande:\n- (Falso) due"
    )


def test_request_contexts_block_is_exposed_in_model_dump() -> None:
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="A", statements=[_statement("a")])]
    )
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
