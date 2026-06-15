from pathlib import Path
from unittest.mock import Mock

import pytest

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_cleaning import (
    CleaningPipeline,
    CleaningPipelineBuilder,
)
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def _build_config(
    cds_parsed_path: Path = FIXTURES_DIR / "cds_sample.json",
    cap_parsed_path: Path = FIXTURES_DIR / "cap_sample.json",
) -> IngestorConfig:
    return IngestorConfig(
        cds_parsed_path=cds_parsed_path,
        cap_parsed_path=cap_parsed_path,
        postgres=PostgresConnectionConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def test_build_raises_when_parsed_source_path_is_missing(tmp_path: Path) -> None:
    cds_parsed_path = tmp_path / "missing-cds.json"
    cap_parsed_path = tmp_path / "missing-cap.json"
    config = _build_config(cds_parsed_path=cds_parsed_path, cap_parsed_path=cap_parsed_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        CleaningPipelineBuilder(config).build()

    assert str(cds_parsed_path) in str(exc_info.value)
    assert str(cap_parsed_path) in str(exc_info.value)


def test_build_uses_overridden_dependencies_instead_of_defaults() -> None:
    article_repository = Mock(spec=ArticleRepository)
    article_cleaner = Mock(spec=ArticleCleaner)

    pipeline = (
        CleaningPipelineBuilder(_build_config())
        .with_article_repository(article_repository)
        .with_article_cleaner(article_cleaner)
        .build()
    )

    assert isinstance(pipeline, CleaningPipeline)
    assert pipeline._article_repository is article_repository
    assert pipeline._article_cleaner is article_cleaner
