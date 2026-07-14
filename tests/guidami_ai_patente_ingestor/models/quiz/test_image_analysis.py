from guidami_ai_patente_ingestor.models.quiz import ImageAnalysis


def test_image_analysis_stores_visual_analysis_name_and_description() -> None:
    img = ImageAnalysis(
        visual_analysis="Segnale ottagonale rosso con scritta STOP.",
        name="Stop",
        description="Segnale di stop ottagonale rosso.",
    )
    assert img.visual_analysis == "Segnale ottagonale rosso con scritta STOP."
    assert img.name == "Stop"
    assert img.description == "Segnale di stop ottagonale rosso."


def test_image_analysis_round_trips_through_json() -> None:
    original = ImageAnalysis(
        visual_analysis="Segnale triangolare giallo con bordo rosso.",
        name="Curva",
        description="Segnale di curva pericolosa.",
    )
    restored = ImageAnalysis.model_validate(original.model_dump())
    assert restored == original
