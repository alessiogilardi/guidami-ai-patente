from pathlib import Path
from unittest.mock import Mock

from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_cleaning import CleaningPipeline
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner


def _build_config(
    tmp_path: Path, cds_cleaned_exists: bool, cap_cleaned_exists: bool
) -> IngestorConfig:
    cds_cleaned_path = tmp_path / "cleaned" / "cds.json"
    cap_cleaned_path = tmp_path / "cleaned" / "cap.json"
    if cds_cleaned_exists:
        cds_cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cds_cleaned_path.write_text("[]", encoding="utf-8")
    if cap_cleaned_exists:
        cap_cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cap_cleaned_path.write_text("[]", encoding="utf-8")

    return IngestorConfig(
        cds_parsed_path=tmp_path / "parsed" / "cds.json",
        cds_cleaned_path=cds_cleaned_path,
        cap_parsed_path=tmp_path / "parsed" / "cap.json",
        cap_cleaned_path=cap_cleaned_path,
        vector_store=VectorStoreConfig(
            host="localhost", user="unused", password="unused", dbname="unused"
        ),
    )


def test_run_cleans_both_sources_when_no_cleaned_output_exists(tmp_path: Path) -> None:
    config = _build_config(tmp_path, cds_cleaned_exists=False, cap_cleaned_exists=False)

    article = Mock()
    cleaned_article = Mock()
    article_repository = Mock(spec=ArticleRepository)
    article_repository.load.return_value = [article]

    article_cleaner = Mock(spec=ArticleCleaner)
    article_cleaner.clean.return_value = cleaned_article

    pipeline = CleaningPipeline(
        article_repository=article_repository,
        article_cleaner=article_cleaner,
        config=config,
    )

    pipeline.run()

    load_calls = [c.args[0] for c in article_repository.load.call_args_list]
    assert load_calls == [config.cds_parsed_path, config.cap_parsed_path]

    write_calls = [c.args for c in article_repository.write.call_args_list]
    assert write_calls == [
        ([cleaned_article], config.cds_cleaned_path),
        ([cleaned_article], config.cap_cleaned_path),
    ]

    assert article_cleaner.clean.call_args_list == [((article,),), ((article,),)]


def test_run_skips_source_when_cleaned_output_already_exists(tmp_path: Path) -> None:
    config = _build_config(tmp_path, cds_cleaned_exists=True, cap_cleaned_exists=False)

    article_repository = Mock(spec=ArticleRepository)
    article_repository.load.return_value = []
    article_cleaner = Mock(spec=ArticleCleaner)

    pipeline = CleaningPipeline(
        article_repository=article_repository,
        article_cleaner=article_cleaner,
        config=config,
    )

    pipeline.run()

    load_calls = [c.args[0] for c in article_repository.load.call_args_list]
    assert load_calls == [config.cap_parsed_path]

    write_calls = [c.args[1] for c in article_repository.write.call_args_list]
    assert write_calls == [config.cap_cleaned_path]
