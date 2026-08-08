from commons.ai.embedding.composition import FieldSpecComposer
from commons.ai.embedding.models import EmbeddingSpec, FieldSpec


def test_compose_joins_labelled_fields_with_default_separator() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m["title"], label="Titolo"),
            FieldSpec(extractor=lambda m: m["body"], label="Testo"),
        ]
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"title": "Art. 1", "body": "Contenuto"})

    assert text == "Titolo: Art. 1\n\nTesto: Contenuto"


def test_compose_renders_bare_value_when_label_is_none() -> None:
    spec = EmbeddingSpec(fields=[FieldSpec(extractor=lambda m: m["title"])])
    composer = FieldSpecComposer(spec)

    text = composer.compose({"title": "Art. 1"})

    assert text == "Art. 1"


def test_compose_skips_none_field_by_default() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m["title"], label="Titolo"),
            FieldSpec(extractor=lambda m: m.get("missing"), label="Note"),
        ]
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"title": "Art. 1"})

    assert text == "Titolo: Art. 1"


def test_compose_includes_none_field_when_skip_if_none_is_false() -> None:
    spec = EmbeddingSpec(
        fields=[FieldSpec(extractor=lambda m: m.get("missing"), label="Note", skip_if_none=False)]
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({})

    assert text == "Note: None"


def test_compose_applies_formatter_before_rendering() -> None:
    spec = EmbeddingSpec(
        fields=[FieldSpec(extractor=lambda m: m["title"], label="Titolo", formatter=str.upper)]
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"title": "art. 1"})

    assert text == "Titolo: ART. 1"


def test_compose_uses_custom_separator() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m["a"]),
            FieldSpec(extractor=lambda m: m["b"]),
        ],
        separator=" | ",
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"a": "x", "b": "y"})

    assert text == "x | y"


def test_compose_normalizes_three_or_more_consecutive_newlines() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m["a"]),
            FieldSpec(extractor=lambda m: m["b"]),
        ],
        separator="\n\n\n\n",
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"a": "x", "b": "y"})

    assert text == "x\n\ny"


def test_compose_strips_leading_and_trailing_whitespace() -> None:
    spec = EmbeddingSpec(fields=[FieldSpec(extractor=lambda m: "  padded  ")])
    composer = FieldSpecComposer(spec)

    text = composer.compose({})

    assert text == "padded"


def test_compose_skips_normalization_when_disabled() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m["a"]),
            FieldSpec(extractor=lambda m: m["b"]),
        ],
        separator="\n\n\n\n",
        normalize_whitespace=False,
    )
    composer = FieldSpecComposer(spec)

    text = composer.compose({"a": "x", "b": "y"})

    assert text == "x\n\n\n\ny"


def test_compose_works_identically_for_object_models() -> None:
    class Article:
        title = "Art. 1"

    spec = EmbeddingSpec(fields=[FieldSpec.from_attr("title", label="Titolo")])
    composer = FieldSpecComposer(spec)

    text = composer.compose(Article())

    assert text == "Titolo: Art. 1"


def test_compose_or_none_returns_none_when_required_field_missing() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m.get("title")),
            FieldSpec(extractor=lambda m: m.get("required"), skip_if_none=False),
        ]
    )
    composer = FieldSpecComposer(spec)

    assert composer.compose_or_none({"title": "Art. 1"}) is None


def test_compose_or_none_returns_text_when_required_field_present() -> None:
    spec = EmbeddingSpec(
        fields=[
            FieldSpec(extractor=lambda m: m.get("title")),
            FieldSpec(extractor=lambda m: m.get("required"), skip_if_none=False),
        ]
    )
    composer = FieldSpecComposer(spec)

    assert composer.compose_or_none({"title": "Art. 1", "required": "x"}) == "Art. 1\n\nx"


def test_compose_or_none_ignores_missing_optional_field() -> None:
    """A default (skip_if_none=True) missing field never triggers the None-return.

    Only skip_if_none=False ("required") fields do.
    """
    spec = EmbeddingSpec(fields=[FieldSpec(extractor=lambda m: m.get("missing"))])
    composer = FieldSpecComposer(spec)

    assert composer.compose_or_none({}) == ""
