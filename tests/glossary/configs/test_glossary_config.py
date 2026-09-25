from pathlib import Path

import pytest
from pydantic import ValidationError

from glossary.configs import GlossaryConfig


@pytest.fixture(autouse=True)
def _agents_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTS_DIR", "configs/agents")


def test_the_shipped_block_list_has_seven_blocks_and_only_real_definition_commas() -> None:
    config = GlossaryConfig(
        postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"}
    )
    assert len(config.blocks) == 7
    cds_art_2_commas = {b.comma_number for b in config.blocks if b.article_number == "2"}
    assert cds_art_2_commas == {"1", "3", "4"}


def test_embedding_column_is_configurable() -> None:
    config = GlossaryConfig(
        postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"},
        embedding_column="embedding_ada_002",
    )
    assert config.embedding_column == "embedding_ada_002"


def test_missing_agents_dir_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTS_DIR", raising=False)
    with pytest.raises(ValidationError):
        GlossaryConfig(postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"})


def test_max_block_chars_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GlossaryConfig(
            postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"},
            max_block_chars=0,
        )


def test_simplification_batch_size_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GlossaryConfig(
            postgres={"host": "localhost", "user": "u", "password": "p", "dbname": "d"},
            simplification_batch_size=0,
        )
