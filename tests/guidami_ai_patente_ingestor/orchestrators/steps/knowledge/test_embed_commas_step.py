"""Tests for EmbedCommasStep."""

from flowstep import FlowContext

from commons.ai.embedding import (
    EmbeddingClient,
    EmbeddingService,
    EmbeddingSpec,
    FieldSpec,
    FieldSpecComposer,
    ModelEmbeddingService,
)
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableArticleComma
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import EmbedCommasStep

# Mirrors knowledge_flows.py's embed_step wiring (title + comma text, one part per
# line, discarding empty parts, no normalization) — kept independent so this test
# module doesn't reach into orchestrators' private module state.
_COMMA_TEXT_SPEC = EmbeddingSpec(
    fields=[
        FieldSpec(extractor=lambda comma: comma.article_title or None),
        FieldSpec(extractor=lambda comma: comma.text or None),
    ],
    separator="\n",
    normalize_whitespace=False,
)


# EMBEDDABLE_ARTICLE_COMMAS is not yet a context_keys.py constant (added in T-14);
# EmbedCommasStep reads/writes it as a hardcoded literal until then (per plan T-11).
_EMBEDDABLE_ARTICLE_COMMAS_KEY = "embeddable_article_commas"

_FIXED_VECTOR = [0.1, 0.2, 0.3]


class _FixedVectorClient(EmbeddingClient):
    """Fake client returning the same fixed vector for every passage."""

    def embed_query(self, text: str) -> list[float]:
        return _FIXED_VECTOR

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [_FIXED_VECTOR for _ in texts]


class _RecordingClient(EmbeddingClient):
    """Fake client that records every text it was asked to embed."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return _FIXED_VECTOR

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [_FIXED_VECTOR for _ in texts]


def _make_service(
    client: EmbeddingClient, batch_size: int = 10
) -> ModelEmbeddingService[EmbeddableArticleComma]:
    composer = FieldSpecComposer[EmbeddableArticleComma](_COMMA_TEXT_SPEC)
    return ModelEmbeddingService(composer, EmbeddingService(batch_size=batch_size, client=client))


def _make_comma(
    article_number: str = "1",
    article_title: str = "Titolo",
    text: str = "Corpo",
    repealed: bool = False,
) -> EmbeddableArticleComma:
    return EmbeddableArticleComma(
        source="cds",
        article_number=article_number,
        article_title=article_title,
        comma_number="1",
        position=0,
        text=text,
        is_repealed=repealed,
    )


def test_embed_commas_skips_repealed_when_embed_repealed_false() -> None:
    normal = _make_comma(article_number="1", repealed=False)
    repealed = _make_comma(article_number="2", repealed=True)
    context = FlowContext({_EMBEDDABLE_ARTICLE_COMMAS_KEY: [normal, repealed]})
    step = EmbedCommasStep(
        "embed_commas",
        embed_repealed=False,
        model_embedding_service=_make_service(_FixedVectorClient()),
    )

    step.execute(context)

    result: list[EmbeddableArticleComma] = context.get(_EMBEDDABLE_ARTICLE_COMMAS_KEY)
    by_article_number = {comma.article_number: comma for comma in result}
    assert by_article_number["2"].embedding is None, "repealed comma must stay unembedded"
    assert by_article_number["1"].embedding == _FIXED_VECTOR, (
        "non-repealed comma must receive the fake service's vector"
    )


def test_embed_commas_input_is_title_plus_text() -> None:
    comma = _make_comma(article_title="Titolo", text="Corpo")
    recording_client = _RecordingClient()
    context = FlowContext({_EMBEDDABLE_ARTICLE_COMMAS_KEY: [comma]})
    step = EmbedCommasStep(
        "embed_commas",
        embed_repealed=False,
        model_embedding_service=_make_service(recording_client),
    )

    step.execute(context)

    assert "Titolo\nCorpo" in recording_client.calls, (
        "title + comma text (no context) must be sent to the embedding client"
    )


def test_embed_commas_input_discards_empty_title() -> None:
    comma = _make_comma(article_title="", text="Corpo")
    recording_client = _RecordingClient()
    context = FlowContext({_EMBEDDABLE_ARTICLE_COMMAS_KEY: [comma]})
    step = EmbedCommasStep(
        "embed_commas",
        embed_repealed=False,
        model_embedding_service=_make_service(recording_client),
    )

    step.execute(context)

    assert "Corpo" in recording_client.calls, "an empty title must be discarded, not embedded"
