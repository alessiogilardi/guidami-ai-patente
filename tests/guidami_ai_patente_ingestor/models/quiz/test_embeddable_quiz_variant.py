from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizVariant


def test_construct() -> None:
    variant = EmbeddableQuizVariant(question_number="1", variant="text", embedding=[0.1])

    assert variant.question_number == "1"
    assert variant.variant == "text"
    assert variant.embedding == [0.1]
