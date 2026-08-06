import inspect

from guidami_ai_patente_ingestor.cli.services.evaluation.adherence_calculator import (
    AdherenceCalculator,
)
from guidami_ai_patente_ingestor.configs import EvaluationConfig


class _FakeCorpusReadRepository:
    """Local double injected into `AdherenceCalculator`, never called.

    `build_tsquery` does no repository round trip: AD-3's constraint is on lexeme
    construction, not on any query.
    """


def test_tsquery_lexemes_are_or_joined() -> None:
    """AD-3: `build_tsquery` returns multiple lexemes for the repository to OR-join.

    Never a single AND-joined `plainto_tsquery`/`websearch_to_tsquery` string, which was
    measured to return 0.0000 on every row of a sample.
    """
    calculator = AdherenceCalculator(EvaluationConfig(), _FakeCorpusReadRepository())

    lexemes = calculator.build_tsquery("Quale segnale indica un divieto di sosta?")

    assert len(lexemes) > 1
    source = inspect.getsource(
        inspect.getmodule(AdherenceCalculator)  # type: ignore[arg-type]
    )
    assert "plainto_tsquery" not in source
    assert "websearch_to_tsquery" not in source
