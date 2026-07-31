"""Tests for build_quiz_indexing_flow (flow factory SP04, single-source full-reload)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from flowstep import Flow, FlowValidator

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.orchestrators import build_quiz_indexing_flow
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
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def _make_embedding_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    client.embed_passages.side_effect = lambda texts: [[float(len(t))] * 1536 for t in texts]
    return client


def _make_postgres_client() -> PostgresClient:
    return MagicMock(spec=PostgresClient)


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


def test_flow_has_five_steps_in_order() -> None:
    """The chain is Load → MapToEmbedded → Embed → MapToQuizEntity → Store."""
    steps = _build().get_steps()
    assert [step.name for step in steps] == [
        "load_enriched_quiz",
        "map_to_embedded",
        "embed_quiz",
        "map_to_quiz_entity",
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
    enriched_path = resolver.path("enriched", "quiz")
    enriched_path.parent.mkdir(parents=True)
    enriched_path.write_text(json.dumps([_enriched_quiz_payload(1)]), encoding="utf-8")

    config = IngestorConfig(
        embedding_batch_size=4,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
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
    assert len(begin_steps) == 5
    assert len(end_steps) == 5
    assert [args[1] for args in begin_steps] == [1, 2, 3, 4, 5]
    # Proves the reporter reached the injected EmbeddingService (via EmbedQuizMetadata).
    assert ("begin_items", ("batches", 1)) in progress_recorder.calls
