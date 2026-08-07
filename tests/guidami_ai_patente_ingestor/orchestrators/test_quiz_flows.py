"""Tests for build_quiz_indexing_flow (flow factory SP04, single-source full-reload)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from flowstep import Flow, FlowValidator
from pydantic import SecretStr

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import build_quiz_indexing_flow
from guidami_ai_patente_ingestor.orchestrators.steps.generic import LoadJsonDirStep
from guidami_ai_patente_ingestor.services import LayerResolver

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _base_config() -> IngestorConfig:
    return IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
        ),
    )


def _make_embedding_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    client.embed_passages.side_effect = lambda texts: [[float(len(t))] * 1536 for t in texts]
    return client


def _make_postgres_client() -> PostgresClient:
    client = MagicMock(spec=PostgresClient)
    # StoreQuizStep (T-8/PD-7) resolves each question's DB id via
    # upsert_returning_ids -> execute_many_returning; a bare MagicMock's default
    # __iter__ (iter([])) would starve the zip(strict=True) that pairs ids back to
    # question numbers, so return one id per row instead.
    client.execute_many_returning.side_effect = lambda query, params_seq: [
        (i + 1,) for i in range(len(params_seq))
    ]
    return client


def _build(validate: bool = False) -> Flow:
    return build_quiz_indexing_flow(
        config=_base_config(),
        layer_resolver=MagicMock(spec=LayerResolver),
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        validate=validate,
    )


# ---------------------------------------------------------------------------
# Unit tests — no filesystem, no DB
# ---------------------------------------------------------------------------


def test_build_returns_flow_instance() -> None:
    assert isinstance(_build(), Flow)


def test_flow_name_is_quiz_indexing() -> None:
    assert _build().name == "quiz_indexing"


def test_flow_required_input_keys_is_empty_set() -> None:
    """The flow requires no external keys: LoadJsonStep starts from scratch."""
    report = FlowValidator().validate(_build())
    assert report.required_input_keys == set()


def test_build_with_validate_true_does_not_raise() -> None:
    """validate=True does not raise (the WARNING on EMBEDDED_QUIZ is benign)."""
    assert isinstance(_build(validate=True), Flow)


def test_flow_has_six_steps_in_order() -> None:
    """Load -> MapToEmbedded -> EmbedVariants -> MapToQuizEntity -> MapToQuizImages -> Store.

    T-9: step 3 now embeds every configured variant, not just quiz_metadata.
    """
    steps = _build().get_steps()
    assert [step.name for step in steps] == [
        "load_enriched_quiz",
        "map_to_embedded",
        "embed_quiz_variants",
        "map_to_quiz_entity",
        "map_to_quiz_images",
        "store_quiz",
    ]


# ---------------------------------------------------------------------------
# Progress reporting (T-10) — real filesystem, stubbed postgres_client, no real DB
# ---------------------------------------------------------------------------


def _enriched_quiz_payload(question_id: int) -> dict:
    return {
        "question_id": question_id,
        "topic": "Segnaletica",
        "number": "1",
        "text": "Domanda di prova.",
        "correct_answer": True,
        "image": None,
        # quiz_metadata must be present: EmbedQuizMetadata only calls EmbeddingService
        # for items that carry it, and this test asserts the reporter reaches that
        # injected service (begin_items("batches", 1)).
        "quiz_metadata": {
            "core_concepts": ["concetto"],
            "exact_keywords": ["parola chiave"],
            "vector_search_queries": ["query di ricerca"],
            "rule_explanation": "Spiegazione breve.",
        },
    }


def test_indexing_flow_reports_step_progress(
    tmp_path: Path, progress_recorder: RecordingProgressReporter
) -> None:
    resolver = LayerResolver(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={"quiz": SourceConfig(dir="quiz", file="quiz.json")},
    )
    enriched_dir = resolver.dir("enriched", "quiz")
    enriched_dir.mkdir(parents=True)
    (enriched_dir / f"{element_id('quiz', '1')}.json").write_text(
        json.dumps(_enriched_quiz_payload(1)), encoding="utf-8"
    )

    config = IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password=SecretStr("unused"), dbname="unused"
        ),
        project_root=tmp_path,
    )

    build_quiz_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=_make_embedding_client(),
        postgres_client=_make_postgres_client(),
        progress=progress_recorder,
    ).run()

    begin_steps = [args for name, args in progress_recorder.calls if name == "begin_step"]
    end_steps = [args for name, args in progress_recorder.calls if name == "end_step"]
    assert len(begin_steps) == 6
    assert len(end_steps) == 6
    assert [args[1] for args in begin_steps] == [1, 2, 3, 4, 5, 6]
    # Proves the reporter reached the injected EmbeddingService (via EmbedQuizMetadata).
    assert ("begin_items", ("batches", 1)) in progress_recorder.calls


def test_build_quiz_indexing_flow_reads_enriched_directory_layer() -> None:
    """T-3: the flow's first step reads EnrichedQuizModel from a per-element directory."""
    load_step = _build().get_steps()[0]
    assert isinstance(load_step, LoadJsonDirStep)
    assert (
        load_step._repository._model_class is EnrichedQuizModel  # type: ignore[attr-defined]  # noqa: SLF001
    )
