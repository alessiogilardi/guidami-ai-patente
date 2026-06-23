from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel


def _question(**kwargs) -> EmbeddableQuizModel:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Il segnale raffigurato preavvisa un incrocio.",
        correct_answer=True,
    )
    return EmbeddableQuizModel(**{**defaults, **kwargs})


def test_embeddable_quiz_question_defaults_image_fields_to_none() -> None:
    q = _question()
    assert q.image_filename is None
    assert q.image_description is None
    assert q.embedding is None


def test_embedded_text_without_image_description() -> None:
    q = _question(topic="Segnaletica", text="Domanda senza immagine.")
    assert q.embedded_text == "Segnaletica Domanda senza immagine."


def test_embedded_text_with_image_description_appends_description() -> None:
    q = _question(
        topic="Segnaletica",
        text="Il segnale raffigurato indica.",
        image_description="Segnale di stop ottagonale rosso.",
    )
    assert q.embedded_text == (
        "Segnaletica Il segnale raffigurato indica. Segnale di stop ottagonale rosso."
    )


def test_embedded_text_with_empty_image_description_omits_description() -> None:
    q = _question(topic="T", text="Testo.", image_description=None)
    assert q.embedded_text == "T Testo."
