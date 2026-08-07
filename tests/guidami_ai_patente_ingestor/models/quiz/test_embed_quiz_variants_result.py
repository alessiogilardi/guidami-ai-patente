from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizVariant, EmbedQuizVariantsResult


def test_default_omitted_counts_is_empty_dict() -> None:
    result = EmbedQuizVariantsResult(variants=[])

    assert result.omitted_counts == {}


def test_construct_with_variants_and_omitted_counts() -> None:
    rows = [EmbeddableQuizVariant(question_number="1", variant="text", embedding=[0.1])]

    result = EmbedQuizVariantsResult(variants=rows, omitted_counts={"search_queries": 1})

    assert result.variants == rows
    assert result.omitted_counts == {"search_queries": 1}
