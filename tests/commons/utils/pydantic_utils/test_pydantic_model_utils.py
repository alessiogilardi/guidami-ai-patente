import pytest
from pydantic import BaseModel

from commons.utils.pydantic_utils import PydanticModelUtils


class _User(BaseModel):
    name: str
    age: int


def test_validate_model_attributes_accepts_valid_fields() -> None:
    PydanticModelUtils.validate_model_attributes(_User, "name", "age")


def test_validate_model_attributes_raises_for_unknown_field() -> None:
    with pytest.raises(ValueError, match="Invalid attributes"):
        PydanticModelUtils.validate_model_attributes(_User, "unknown")


def test_validate_model_attributes_raises_when_no_attributes_given() -> None:
    with pytest.raises(ValueError, match="At least one attribute"):
        PydanticModelUtils.validate_model_attributes(_User)
