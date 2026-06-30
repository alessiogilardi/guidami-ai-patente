"""Tests for ArticleContextualizerRequest and ArticleContextualizerResponse DTOs."""


def test_request_accepts_title_text_paragraphs_as_strings() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerRequest,
    )

    req = ArticleContextualizerRequest(
        title="Finalità del codice",
        text="La circolazione stradale è regolata dal presente codice.",
        paragraphs="1. Le norme del presente codice.\n2. Si applicano.",
    )
    assert req.title == "Finalità del codice"
    assert req.text == "La circolazione stradale è regolata dal presente codice."
    assert req.paragraphs == "1. Le norme del presente codice.\n2. Si applicano."


def test_request_paragraphs_is_str_not_list() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerRequest,
    )

    req = ArticleContextualizerRequest(title="T", text="X", paragraphs="1. Comma.")
    assert isinstance(req.paragraphs, str), (
        f"paragraphs must be str but got {type(req.paragraphs)}"
    )


def test_request_has_exactly_title_text_paragraphs_fields() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerRequest,
    )

    fields = set(ArticleContextualizerRequest.model_fields.keys())
    assert fields == {"title", "text", "paragraphs"}, (
        f"Expected {{title, text, paragraphs}}, got {fields}"
    )


def test_response_class_exists_and_has_contexts_field() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerResponse,
    )

    resp = ArticleContextualizerResponse(contexts={0: "Primo contesto.", 1: "Secondo."})
    assert resp.contexts == {0: "Primo contesto.", 1: "Secondo."}


def test_response_contexts_keys_are_int() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerResponse,
    )

    resp = ArticleContextualizerResponse(contexts={0: "ctx", 1: "ctx2"})
    assert all(isinstance(k, int) for k in resp.contexts), "contexts keys must be int, not str"


def test_response_has_exactly_contexts_field() -> None:
    from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
        ArticleContextualizerResponse,
    )

    fields = set(ArticleContextualizerResponse.model_fields.keys())
    assert fields == {"contexts"}, f"Expected {{contexts}}, got {fields}"
