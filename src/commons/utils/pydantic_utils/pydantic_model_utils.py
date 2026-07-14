"""Utilities for Pydantic model validation."""

from pydantic import BaseModel


class PydanticModelUtils:
    """Utilities for Pydantic model validation."""

    @staticmethod
    def validate_model_attributes(
        model: type[BaseModel],
        *attributes: str,
    ) -> None:
        """Validate that all specified attributes exist as fields on a Pydantic model.

        Requires at least one attribute to be provided, similar to Pydantic's
        field_validator decorator behavior.

        Args:
            model: The Pydantic model class to validate against
            *attributes: One or more attribute names to check (at least one required)

        Raises:
            ValueError: If no attributes are provided, or if any attributes don't
                    exist on the model

        Example:
            >>> from pydantic import BaseModel
            >>> class User(BaseModel):
            ...     name: str
            ...     age: int
            >>> validate_model_attributes(User, "name", "age")  # OK
            >>> validate_model_attributes(User, "name", "invalid")  # Raises ValueError
            >>> validate_model_attributes(User)  # Raises ValueError - no attributes
        """
        if not attributes:
            raise ValueError("At least one attribute must be provided for validation")

        valid_fields = set(model.model_fields.keys())
        invalid = set(attributes) - valid_fields

        if invalid:
            raise ValueError(
                f"Invalid attributes for {model.__name__}: {sorted(invalid)}. "
                f"Valid attributes are: {sorted(valid_fields)}"
            )
