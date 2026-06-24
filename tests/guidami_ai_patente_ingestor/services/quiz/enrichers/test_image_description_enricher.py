"""Test per ImageDescriptionEnricher."""

from pathlib import Path
from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, ImageDescription
from guidami_ai_patente_ingestor.services.quiz.enrichers import ImageDescriptionEnricher


def _question(
    number: str,
    question_id: int = 1,
    image: str | None = None,
    image_description: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=question_id,
        topic="Segnaletica",
        number=number,
        text="Domanda.",
        correct_answer=True,
        image=image,
        image_description=image_description,
    )


def _make_describer(name: str = "Stop", description: str = "Segnale rosso.") -> MagicMock:
    describer = MagicMock(spec=RoadSignDescriberAgent)
    describer.describe.return_value = ImageDescription(name=name, description=description)
    return describer


def test_enrich_dedups_calls_for_repeated_image(tmp_path: Path) -> None:
    (tmp_path / "a.jpeg").write_bytes(b"\x00")
    (tmp_path / "b.jpeg").write_bytes(b"\x00")
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    questions = [
        _question("1", image="a.jpeg"),
        _question("2", image="a.jpeg"),
        _question("3", image="b.jpeg"),
    ]

    enricher.enrich(questions)

    assert describer.describe.call_count == 2


def test_enrich_sets_formatted_description_on_matching_sub_questions(tmp_path: Path) -> None:
    (tmp_path / "stop.jpeg").write_bytes(b"\x00")
    describer = _make_describer(name="Stop", description="Segnale rosso ottagonale.")
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    questions = [_question("1", image="stop.jpeg")]

    result = enricher.enrich(questions)

    assert result[0].image_description == "Stop. Segnale rosso ottagonale."


def test_enrich_missing_file_skips_and_warns(tmp_path: Path, caplog) -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    questions = [_question("1", image="missing.jpeg")]

    with caplog.at_level("WARNING"):
        result = enricher.enrich(questions)

    assert result[0].image_description is None
    describer.describe.assert_not_called()
    assert any("missing.jpeg" in record.message for record in caplog.records)


def test_enrich_describe_raising_skips_and_warns(tmp_path: Path, caplog) -> None:
    (tmp_path / "stop.jpeg").write_bytes(b"\x00")
    describer = _make_describer()
    describer.describe.side_effect = RuntimeError("vision call failed")
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    questions = [_question("1", image="stop.jpeg")]

    with caplog.at_level("WARNING"):
        result = enricher.enrich(questions)

    assert result[0].image_description is None
    assert any("stop.jpeg" in record.message for record in caplog.records)


def test_enrich_no_image_means_description_stays_none(tmp_path: Path) -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    questions = [_question("1", image=None)]

    result = enricher.enrich(questions)

    assert result[0].image_description is None
    describer.describe.assert_not_called()


def test_enrich_does_not_mutate_input_models(tmp_path: Path) -> None:
    (tmp_path / "stop.jpeg").write_bytes(b"\x00")
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(describer, tmp_path)
    original = _question("1", image="stop.jpeg")
    questions = [original]

    enricher.enrich(questions)

    assert original.image_description is None
