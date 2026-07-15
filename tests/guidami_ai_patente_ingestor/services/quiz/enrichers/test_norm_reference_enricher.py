"""Tests for NormReferenceEnricher."""

from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.agents import NormReferenceDescriberAgent
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


def _question(
    number: str,
    *,
    topic: str = "Segnaletica",
    text: str = "Domanda.",
    correct_answer: bool = True,
    image: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=1,
        topic=topic,
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
    )


def _make_agent_mock() -> MagicMock:
    """Fake agent exposing an async `run` (auto-detected as AsyncMock via `spec`)."""
    agent = MagicMock(spec=NormReferenceDescriberAgent)
    response = MagicMock()
    response.core_concepts = ["concetto"]
    response.exact_keywords = ["parola chiave"]
    response.vector_search_queries = ["query di ricerca"]
    response.rule_explanation = "Spiegazione breve."
    agent.run.return_value = response
    return agent


async def test_dedup_calls() -> None:
    from guidami_ai_patente_ingestor.services.quiz.enrichers import NormReferenceEnricher

    agent = _make_agent_mock()
    enricher = NormReferenceEnricher(8, agent)
    questions = [
        _question("1", topic="T", text="Q", correct_answer=True, image="img.jpeg"),
        _question("2", topic="T", text="Q", correct_answer=True, image="img.jpeg"),
        _question("3", topic="T", text="Q", correct_answer=True, image="img.jpeg"),
    ]

    await enricher(questions)

    assert agent.run.call_count == 1, (
        f"Expected 1 agent call for 3 identical questions, got {agent.run.call_count}"
    )


async def test_propagates_to_all_matching_rows() -> None:
    from guidami_ai_patente_ingestor.services.quiz.enrichers import NormReferenceEnricher

    agent = _make_agent_mock()
    enricher = NormReferenceEnricher(8, agent)
    questions = [
        _question("1", topic="T", text="Q", correct_answer=True, image="img.jpeg"),
        _question("2", topic="T", text="Q", correct_answer=True, image="img.jpeg"),
    ]

    result = await enricher(questions)

    assert result[0].quiz_metadata is not None, "quiz_metadata should be set on first matching row"
    assert result[1].quiz_metadata is not None, (
        "quiz_metadata should be set on second matching row"
    )


async def test_agent_failure_skips_question(caplog) -> None:
    from guidami_ai_patente_ingestor.services.quiz.enrichers import NormReferenceEnricher

    agent = MagicMock(spec=NormReferenceDescriberAgent)
    agent.run.side_effect = RuntimeError("agent call failed")
    enricher = NormReferenceEnricher(8, agent)
    questions = [_question("1")]

    with caplog.at_level("WARNING"):
        result = await enricher(questions)

    assert result[0].quiz_metadata is None, "quiz_metadata should remain None when agent fails"
    assert any(record.levelname == "WARNING" for record in caplog.records), (
        "expected a WARNING log entry when the agent raises"
    )
    # Per Decision 7 (no traceback on the WARNING degrade path).
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert all(record.exc_info is None for record in warning_records)


async def test_unique_questions_each_get_a_call() -> None:
    from guidami_ai_patente_ingestor.services.quiz.enrichers import NormReferenceEnricher

    agent = _make_agent_mock()
    enricher = NormReferenceEnricher(8, agent)
    questions = [
        _question("1", topic="Topic A", text="Domanda A", correct_answer=True),
        _question("2", topic="Topic B", text="Domanda B", correct_answer=False),
        _question("3", topic="Topic C", text="Domanda C", correct_answer=True),
    ]

    await enricher(questions)

    assert agent.run.call_count == 3, (
        f"Expected 3 agent calls for 3 distinct questions, got {agent.run.call_count}"
    )
