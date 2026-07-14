"""Tests for RoadSignDescriberRequest and RoadSignDescriberResponse DTOs."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import RoadSignDescriberRequest


def test_request_accepts_a_list_of_contexts() -> None:
    request = RoadSignDescriberRequest(
        contexts=["Argomento: A — Testo: uno", "Argomento: B — Testo: due"]
    )
    assert request.contexts == ["Argomento: A — Testo: uno", "Argomento: B — Testo: due"]


def test_request_contexts_block_renders_bullet_list() -> None:
    request = RoadSignDescriberRequest(contexts=["a", "b"])
    assert request.contexts_block == "- a\n- b"


def test_request_contexts_block_is_exposed_in_model_dump() -> None:
    request = RoadSignDescriberRequest(contexts=["a"])
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
