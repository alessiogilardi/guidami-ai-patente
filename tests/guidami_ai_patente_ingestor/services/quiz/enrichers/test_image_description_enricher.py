"""Tests for ImageDescriptionEnricher (grouped by image, one call per image, async)."""

from pathlib import Path
from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, ImageAnalysis
from guidami_ai_patente_ingestor.services.quiz.enrichers import ImageDescriptionEnricher


def _question(
    number: str,
    question_id: int = 1,
    topic: str = "Segnaletica",
    text: str = "Domanda.",
    image: str | None = None,
    image_description: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=question_id,
        topic=topic,
        number=number,
        text=text,
        correct_answer=True,
        image=image,
        image_description=image_description,
    )


def _make_describer(name: str = "Stop", description: str = "Segnale rosso.") -> MagicMock:
    """Fake agent exposing an async `run` (auto-detected as AsyncMock via `spec`)."""
    describer = MagicMock(spec=RoadSignDescriberAgent)
    describer.run.return_value = RoadSignDescriberResponse(
        visual_analysis="Analisi visiva di test.", name=name, description=description
    )
    return describer


def test_enrich_calls_once_per_image_regardless_of_distinct_texts() -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [
        _question("1", image="a.jpeg", topic="Segnaletica", text="Prima domanda."),
        _question("2", image="a.jpeg", topic="Segnaletica", text="Seconda domanda."),
    ]

    result = enricher(questions)

    assert describer.run.call_count == 1
    assert result[0].image_description == result[1].image_description
    assert result[0].image_analysis == result[1].image_analysis
    assert result[0].image_analysis == ImageAnalysis(
        visual_analysis="Analisi visiva di test.", name="Stop", description="Segnale rosso."
    )


def test_enrich_single_call_carries_both_distinct_contexts() -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [
        _question("1", image="a.jpeg", topic="Segnaletica", text="Prima domanda."),
        _question("2", image="a.jpeg", topic="Precedenza", text="Seconda domanda."),
    ]

    enricher(questions)

    request_dto = describer.run.call_args_list[0].args[0]
    assert isinstance(request_dto, RoadSignDescriberRequest)
    assert request_dto.contexts == [
        "Argomento: Segnaletica — Testo: Prima domanda.",
        "Argomento: Precedenza — Testo: Seconda domanda.",
    ]


def test_enrich_calls_once_per_distinct_image() -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [
        _question("1", image="a.jpeg"),
        _question("2", image="a.jpeg"),
        _question("3", image="b.jpeg"),
    ]

    enricher(questions)

    assert describer.run.call_count == 2
    called_images = {call.kwargs["images"][0] for call in describer.run.call_args_list}
    assert called_images == {Path("a.jpeg"), Path("b.jpeg")}


def test_enrich_no_image_means_description_stays_none_and_no_call() -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [_question("1", image=None)]

    result = enricher(questions)

    assert result[0].image_description is None
    describer.run.assert_not_called()


def test_enrich_failing_image_degrades_alone_others_still_described(caplog) -> None:
    describer = MagicMock(spec=RoadSignDescriberAgent)

    def _side_effect(
        request: RoadSignDescriberRequest, images: tuple[Path, ...]
    ) -> RoadSignDescriberResponse:
        if images[0].name == "missing.jpeg":
            raise FileNotFoundError("missing.jpeg")
        return RoadSignDescriberResponse(
            visual_analysis="Analisi.", name="Stop", description="Segnale rosso."
        )

    describer.run.side_effect = _side_effect
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [
        _question("1", image="missing.jpeg"),
        _question("2", image="ok.jpeg"),
    ]

    with caplog.at_level("WARNING"):
        result = enricher(questions)

    missing_result = next(q for q in result if q.image == "missing.jpeg")
    ok_result = next(q for q in result if q.image == "ok.jpeg")
    assert missing_result.image_description is None
    assert ok_result.image_description == "Stop. Segnale rosso."
    assert any("missing.jpeg" in record.message for record in caplog.records)


def test_enrich_describe_raising_generic_exception_degrades_that_image_only(caplog) -> None:
    describer = MagicMock(spec=RoadSignDescriberAgent)

    def _side_effect(
        request: RoadSignDescriberRequest, images: tuple[Path, ...]
    ) -> RoadSignDescriberResponse:
        if images[0].name == "broken.jpeg":
            raise RuntimeError("vision call failed")
        return RoadSignDescriberResponse(
            visual_analysis="Analisi.", name="Stop", description="Segnale rosso."
        )

    describer.run.side_effect = _side_effect
    enricher = ImageDescriptionEnricher(4, describer)
    questions = [
        _question("1", image="broken.jpeg"),
        _question("2", image="ok.jpeg"),
    ]

    with caplog.at_level("WARNING"):
        result = enricher(questions)

    broken_result = next(q for q in result if q.image == "broken.jpeg")
    ok_result = next(q for q in result if q.image == "ok.jpeg")
    assert broken_result.image_description is None
    assert ok_result.image_description == "Stop. Segnale rosso."
    assert any("broken.jpeg" in record.message for record in caplog.records)


def test_enrich_does_not_mutate_input_models() -> None:
    describer = _make_describer()
    enricher = ImageDescriptionEnricher(4, describer)
    original = _question("1", image="stop.jpeg")
    questions = [original]

    enricher(questions)

    assert original.image_description is None
