import dataclasses

import pytest
from commons.ai.embedding.composition import TemplateComposer
from pydantic import BaseModel


class _ArticleModel(BaseModel):
    title: str
    body: str


@dataclasses.dataclass
class _ArticleDataclass:
    title: str
    body: str


def test_compose_substitutes_fields_from_base_model() -> None:
    composer = TemplateComposer("Titolo: $title\nTesto: $body")

    text = composer.compose(_ArticleModel(title="Art. 1", body="Contenuto"))

    assert text == "Titolo: Art. 1\nTesto: Contenuto"


def test_compose_substitutes_fields_from_dataclass() -> None:
    composer = TemplateComposer("Titolo: $title\nTesto: $body")

    text = composer.compose(_ArticleDataclass(title="Art. 1", body="Contenuto"))

    assert text == "Titolo: Art. 1\nTesto: Contenuto"


def test_compose_substitutes_fields_from_mapping() -> None:
    composer = TemplateComposer("Titolo: $title\nTesto: $body")

    text = composer.compose({"title": "Art. 1", "body": "Contenuto"})

    assert text == "Titolo: Art. 1\nTesto: Contenuto"


def test_compose_raises_key_error_on_missing_placeholder() -> None:
    composer = TemplateComposer("Titolo: $title\nTesto: $body")

    with pytest.raises(KeyError):
        composer.compose({"title": "Art. 1"})


def test_compose_raises_type_error_on_unsupported_model_type() -> None:
    composer = TemplateComposer("Titolo: $title")

    with pytest.raises(TypeError):
        composer.compose(42)  # type: ignore[arg-type]
