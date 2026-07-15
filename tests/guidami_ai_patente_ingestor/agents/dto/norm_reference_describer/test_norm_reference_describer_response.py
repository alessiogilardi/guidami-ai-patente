"""Tests for NormReferenceDescriberResponse (entities field removal)."""

from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberResponse,
)


def test_entities_field_removed() -> None:
    assert "entities" not in NormReferenceDescriberResponse.model_fields, (
        "NormReferenceDescriberResponse must no longer declare an 'entities' field"
    )
