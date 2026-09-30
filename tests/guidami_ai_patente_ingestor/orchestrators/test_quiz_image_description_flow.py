"""Tests for build_quiz_image_description_flow (spec 0023, FR-4): real filesystem, no LLM."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flowstep import Flow, FlowExecutionError
from pydantic import SecretStr
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.exceptions import UnknownImageError
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import build_quiz_image_description_flow
from guidami_ai_patente_ingestor.providers import LayerResolverProvider

_PROVIDER = OpenRouterProvider(api_key="test-key")
_OLD = "Vecchio nome. Vecchia descrizione."


def _resolver(tmp_path: Path) -> LayerResolverProvider:
    return LayerResolverProvider(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={"quiz": SourceConfig(dir="quiz", file="quiz.json")},
    )


def _config(tmp_path: Path) -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
        ),
        project_root=tmp_path,
    )


def _quiz(number: str, image: str | None, correct_answer: bool = True) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=1,
        topic="Segnaletica",
        number=number,
        text=f"Domanda {number}.",
        correct_answer=correct_answer,
        image=image,
        image_description=_OLD if image else None,
    )


def _seed(tmp_path: Path, quizzes: list[EnrichedQuizModel]) -> Path:
    directory = _resolver(tmp_path).dir("enriched", "quiz")
    directory.mkdir(parents=True)
    for quiz in quizzes:
        (directory / f"{element_id('quiz', quiz.number)}.json").write_text(
            quiz.model_dump_json(), encoding="utf-8"
        )
    return directory


def _read(directory: Path, number: str) -> EnrichedQuizModel:
    path = directory / f"{element_id('quiz', number)}.json"
    return EnrichedQuizModel.model_validate_json(path.read_text(encoding="utf-8"))


def _describer(response: RoadSignDescriberResponse | Exception) -> MagicMock:
    describer = MagicMock(spec=RoadSignDescriberAgent)
    if isinstance(response, Exception):
        describer.run.side_effect = response
    else:
        describer.run.return_value = response
    return describer


_NEW = RoadSignDescriberResponse(
    visual_analysis="Pannello verde.", name="Onda verde", description="Velocità consigliata."
)


def _run(tmp_path: Path, describer: MagicMock, images: tuple[str, ...] = ()) -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=describer):
        build_quiz_image_description_flow(
            config=_config(tmp_path),
            layer_resolver=_resolver(tmp_path),
            open_router_provider=_PROVIDER,
            images=images,
        ).run()


def test_flow_is_named_and_has_four_steps_in_order(tmp_path: Path) -> None:
    with patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_describer(_NEW)):
        flow = build_quiz_image_description_flow(
            config=_config(tmp_path),
            layer_resolver=_resolver(tmp_path),
            open_router_provider=_PROVIDER,
            validate=True,
        )

    assert isinstance(flow, Flow)
    assert flow.name == "quiz_image_descriptions"
    assert [step.name for step in flow.get_steps()] == [
        "load_enriched_quiz",
        "filter_quiz_by_image",
        "describe_images",
        "write_enriched_quiz",
    ]


def test_regeneration_rewrites_only_the_image_fields_of_the_named_image(tmp_path: Path) -> None:
    directory = _seed(
        tmp_path,
        [
            _quiz("1", "a.jpeg", True),
            _quiz("2", "a.jpeg", False),
            _quiz("3", "b.jpeg"),
            _quiz("4", None),
        ],
    )
    untouched = {n: (directory / f"{element_id('quiz', n)}.json").read_bytes() for n in ("3", "4")}
    describer = _describer(_NEW)

    _run(tmp_path, describer, images=("a.jpeg",))

    assert describer.run.call_count == 1
    for number in ("1", "2"):
        rewritten = _read(directory, number)
        assert rewritten.image_description == "Onda verde. Velocità consigliata."
        assert rewritten.image_analysis is not None
        assert rewritten.image_analysis.name == "Onda verde"
    assert _read(directory, "1").text == "Domanda 1."
    for number, content in untouched.items():
        assert (directory / f"{element_id('quiz', number)}.json").read_bytes() == content


def test_describer_sees_every_question_of_the_image_with_its_answer(tmp_path: Path) -> None:
    _seed(tmp_path, [_quiz("1", "a.jpeg", True), _quiz("2", "a.jpeg", False)])
    describer = _describer(_NEW)

    _run(tmp_path, describer, images=("a.jpeg",))

    request = describer.run.call_args.args[0]
    assert isinstance(request, RoadSignDescriberRequest)
    assert "- (Vero) Domanda 1." in request.contexts_block
    assert "- (Falso) Domanda 2." in request.contexts_block


def test_without_image_filter_every_image_is_described(tmp_path: Path) -> None:
    directory = _seed(tmp_path, [_quiz("1", "a.jpeg"), _quiz("2", "b.jpeg"), _quiz("3", None)])
    describer = _describer(_NEW)

    _run(tmp_path, describer)

    assert describer.run.call_count == 2
    assert _read(directory, "1").image_description == "Onda verde. Velocità consigliata."
    assert _read(directory, "2").image_description == "Onda verde. Velocità consigliata."
    assert _read(directory, "3").image_description is None


def test_failed_description_keeps_the_old_description(tmp_path: Path) -> None:
    """Review Focus 2: a missing image file degrades per image, the old text survives."""
    directory = _seed(tmp_path, [_quiz("1", "a.jpeg")])

    _run(tmp_path, _describer(FileNotFoundError("a.jpeg")), images=("a.jpeg",))

    assert _read(directory, "1").image_description == _OLD


def test_unknown_image_aborts_before_any_llm_call_or_write(tmp_path: Path) -> None:
    directory = _seed(tmp_path, [_quiz("1", "a.jpeg")])
    before = (directory / f"{element_id('quiz', '1')}.json").read_bytes()
    describer = _describer(_NEW)

    with pytest.raises(FlowExecutionError) as excinfo:
        _run(tmp_path, describer, images=("a.jpeg", "nope.jpeg"))

    assert isinstance(excinfo.value.original_error, UnknownImageError)
    assert describer.run.call_count == 0
    assert (directory / f"{element_id('quiz', '1')}.json").read_bytes() == before
