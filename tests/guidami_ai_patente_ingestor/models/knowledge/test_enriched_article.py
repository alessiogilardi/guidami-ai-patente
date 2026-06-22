from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle


def _article(**kwargs) -> EnrichedArticle:
    defaults = dict(
        number="1",
        title="Finalità",
        text="Testo del comma 0.",
        paragraphs=["Primo comma.", "Secondo comma."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )
    return EnrichedArticle(**{**defaults, **kwargs})


def test_enriched_article_defaults_contexts_to_empty_dict() -> None:
    article = _article()
    assert article.contexts == {}


def test_enriched_article_accepts_contexts_keyed_by_comma_index() -> None:
    contexts = {0: "Il comma definisce lo scopo.", 1: "Il comma elenca gli obblighi."}
    article = _article(contexts=contexts)
    assert article.contexts[0] == "Il comma definisce lo scopo."
    assert article.contexts[1] == "Il comma elenca gli obblighi."


def test_enriched_article_round_trips_through_json() -> None:
    contexts = {0: "Contesto.", 1: "Altro contesto."}
    original = _article(contexts=contexts)
    restored = EnrichedArticle.model_validate(original.model_dump())
    assert restored.contexts == original.contexts
    assert restored.number == original.number
