import dataclasses

import pytest

from commons.ai.embedding.models import FieldSpec


def test_from_attr_extracts_value_from_dict() -> None:
    field = FieldSpec.from_attr("title")

    assert field.extractor({"title": "Art. 1"}) == "Art. 1"


def test_from_attr_extracts_value_from_object() -> None:
    class Article:
        title = "Art. 2"

    field = FieldSpec.from_attr("title")

    assert field.extractor(Article()) == "Art. 2"


def test_from_attr_returns_none_for_missing_dict_key() -> None:
    field = FieldSpec.from_attr("missing")

    assert field.extractor({"title": "Art. 1"}) is None


def test_from_attr_returns_none_for_missing_attribute() -> None:
    class Article:
        title = "Art. 1"

    field = FieldSpec.from_attr("missing")

    assert field.extractor(Article()) is None


def test_from_attr_carries_label_and_formatter() -> None:
    formatter = str.upper
    field = FieldSpec.from_attr("title", label="Titolo", formatter=formatter)

    assert field.label == "Titolo"
    assert field.formatter is formatter


def test_from_attr_defaults_skip_if_none_to_true() -> None:
    field = FieldSpec.from_attr("title")

    assert field.skip_if_none is True


def test_from_attr_accepts_skip_if_none_override() -> None:
    field = FieldSpec.from_attr("title", skip_if_none=False)

    assert field.skip_if_none is False


def test_field_spec_is_frozen() -> None:
    field = FieldSpec.from_attr("title")

    with pytest.raises(dataclasses.FrozenInstanceError):
        field.label = "changed"  # type: ignore[misc]
