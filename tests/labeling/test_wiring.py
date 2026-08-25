import inspect
from pathlib import Path
from unittest.mock import MagicMock

from commons.repositories.db import CorpusReadRepository
from domain.models.retrieval import QuizEvaluationRow
from labeling import wiring
from labeling.configs import LabelingConfig
from labeling.services import CandidateSetService, QuestionLexemeService


class _StubLexemeService:
    """Local stand-in for `QuestionLexemeService`, avoiding a dependency on it."""

    def build(self, row: QuizEvaluationRow) -> list[str]:
        return ["'x'"]


def _make_row() -> QuizEvaluationRow:
    return QuizEvaluationRow(
        id=1,
        number="1",
        topic="Segnaletica",
        text="Il segnale indica obbligo di fermata.",
        correct_answer=True,
        exact_keywords=None,
        image_filename=None,
        image_description=None,
        embedding=[0.1, 0.2],
    )


def test_no_builder_takes_an_ingestor_config() -> None:
    offending = []
    for name, builder in inspect.getmembers(wiring, inspect.isfunction):
        for parameter in inspect.signature(builder).parameters.values():
            annotation = str(parameter.annotation)
            if "IngestorConfig" in annotation or "AppConfig" in annotation:
                offending.append((name, parameter.name))

    assert offending == [], "AD-16/AD-27: builders are parameterised on LabelingConfig and values"


def test_the_comma_labeler_config_is_loaded_from_the_given_agents_dir() -> None:
    agent_config = wiring.build_comma_labeler_config(Path("configs/agents"))

    assert agent_config.model_name.startswith("openrouter/")
    assert agent_config.system.strip() != ""


def test_the_lexeme_service_receives_the_configured_fields() -> None:
    config = LabelingConfig(agents_dir=Path("configs/agents"))  # type: ignore[call-arg]

    service = wiring.build_question_lexeme_service(config, corpus_repository=None)  # type: ignore[arg-type]

    assert isinstance(service, QuestionLexemeService)


def test_the_candidate_set_service_receives_both_arm_depths() -> None:
    config = LabelingConfig(agents_dir=Path("configs/agents"), dense_k=7, text_k=9)  # type: ignore[call-arg]
    corpus_repository = MagicMock(spec=CorpusReadRepository)
    corpus_repository.dense_top_k.return_value = []
    corpus_repository.text_match_top_k.return_value = []

    service = wiring.build_candidate_set_service(config, corpus_repository, _StubLexemeService())
    service.build(_make_row())

    assert isinstance(service, CandidateSetService)
    corpus_repository.dense_top_k.assert_called_once()
    assert corpus_repository.dense_top_k.call_args.args[1] == 7
    corpus_repository.text_match_top_k.assert_called_once()
    assert corpus_repository.text_match_top_k.call_args.args[1] == 9
