import pytest
from pydantic import ValidationError

from glossary.agents.glossary_definition_simplifier.dto import SimplifiedDefinitionItemDto


def test_a_whitespace_only_definition_plain_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        SimplifiedDefinitionItemDto(definition_plain="   ")


def test_a_definition_plain_over_400_characters_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SimplifiedDefinitionItemDto(definition_plain="x" * 401)


def test_a_real_definition_plain_is_accepted() -> None:
    dto = SimplifiedDefinitionItemDto(
        definition_plain="La carreggiata è la parte della strada per i veicoli."
    )
    assert dto.definition_plain.startswith("La carreggiata")
