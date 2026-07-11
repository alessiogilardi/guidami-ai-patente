from commons.services.embeddings import Embeddable
from guidami_ai_patente_ingestor.models.quiz import QuizMetadata


def _metadata(**kwargs) -> QuizMetadata:
    defaults = dict(
        core_concepts=["Obbligo di arresto"],
        entities=["segnale di stop"],
        exact_keywords=["obbligo di arresto"],
        vector_search_queries=["prima query di ricerca", "seconda query di ricerca"],
        rule_explanation="Il segnale di stop impone l'obbligo di arresto.",
    )
    return QuizMetadata(**{**defaults, **kwargs})


def test_embedded_text_joins_vector_search_queries_with_newline() -> None:
    metadata = _metadata(vector_search_queries=["prima query", "seconda query"])
    assert metadata.embedded_text == "prima query\nseconda query"


def test_embedded_text_with_single_query_omits_newline() -> None:
    metadata = _metadata(vector_search_queries=["unica query"])
    assert metadata.embedded_text == "unica query"


def test_quiz_metadata_satisfies_embeddable_protocol() -> None:
    """Duck typing: QuizMetadata must satisfy Embeddable without explicit inheritance."""
    assert isinstance(_metadata(), Embeddable)
