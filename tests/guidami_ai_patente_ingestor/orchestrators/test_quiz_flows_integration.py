"""FR-4 verification (spec 0008).

Quiz indexing makes no LLM calls and its row count matches the enriched layer's file
count.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from psycopg import sql

from commons.ai.embedding import EmbeddingClient
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.utils import element_id
from guidami_ai_patente_ingestor.configs import IngestorConfig, SourceConfig
from guidami_ai_patente_ingestor.orchestrators import build_quiz_indexing_flow
from guidami_ai_patente_ingestor.providers import LayerResolverProvider


def _make_embedding_client() -> EmbeddingClient:
    client = MagicMock(spec=EmbeddingClient)
    client.embed_passages.side_effect = lambda texts: [[float(len(t))] * 1536 for t in texts]
    return client


def _enriched_quiz_payload(number: str, question_id: int) -> dict:
    return {
        "question_id": question_id,
        "topic": "Segnaletica",
        "number": number,
        "text": f"Domanda di prova {number}.",
        "correct_answer": True,
        "image": None,
        "quiz_metadata": {
            "core_concepts": ["concetto"],
            "exact_keywords": ["parola chiave"],
            "vector_search_queries": ["query di ricerca"],
            "rule_explanation": "Spiegazione breve.",
        },
    }


@pytest.mark.integration
def test_quiz_indexing_makes_no_llm_calls_and_matches_enriched_file_count(
    tmp_path: Path, postgres_test_config: PostgresConnectionConfig
) -> None:
    pg_client = PostgresClient(postgres_test_config)
    pg_client.truncate("llm_call_logs")
    pg_client.truncate("quiz_question_embeddings", "quiz_questions")
    pg_client.truncate("quiz_images")

    resolver = LayerResolverProvider(
        layers={"enriched": str(tmp_path / "enriched")},
        sources={"quiz": SourceConfig(dir="quiz", file="quiz.json")},
    )
    enriched_dir = resolver.dir("enriched", "quiz")
    enriched_dir.mkdir(parents=True)
    fixture_numbers = ["1", "2", "3"]
    for number in fixture_numbers:
        (enriched_dir / f"{element_id('quiz', number)}.json").write_text(
            json.dumps(_enriched_quiz_payload(number, int(number))), encoding="utf-8"
        )

    config = IngestorConfig(
        embedding_batch_size=4, postgres=postgres_test_config, project_root=tmp_path
    )

    build_quiz_indexing_flow(
        config=config,
        layer_resolver=resolver,
        embedding_client=_make_embedding_client(),
        postgres_client=pg_client,
    ).run()

    llm_call_count = pg_client.fetch(sql.SQL("SELECT count(*) FROM llm_call_logs"))[0][0]
    quiz_question_count = pg_client.fetch(sql.SQL("SELECT count(*) FROM quiz_questions"))[0][0]
    pg_client.close()

    assert llm_call_count == 0, "quiz indexing must never call an LLM agent"
    assert quiz_question_count == len(fixture_numbers)
