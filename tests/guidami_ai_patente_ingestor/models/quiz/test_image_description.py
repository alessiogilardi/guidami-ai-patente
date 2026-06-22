from guidami_ai_patente_ingestor.models.quiz import ImageDescription


def test_image_description_stores_name_and_description() -> None:
    img = ImageDescription(name="Stop", description="Segnale di stop ottagonale rosso.")
    assert img.name == "Stop"
    assert img.description == "Segnale di stop ottagonale rosso."


def test_image_description_round_trips_through_json() -> None:
    original = ImageDescription(name="Curva", description="Segnale di curva pericolosa.")
    restored = ImageDescription.model_validate(original.model_dump())
    assert restored.name == original.name
    assert restored.description == original.description
