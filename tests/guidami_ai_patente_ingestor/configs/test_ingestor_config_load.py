from pathlib import Path

from pydantic import SecretStr

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig


def _postgres(**overrides: object) -> PostgresConnectionConfig:
    return PostgresConnectionConfig(
        **{
            "host": "localhost",
            "user": "unused",
            "password": SecretStr("unused"),
            "dbname": "unused",
            **overrides,
        }
    )


def test_load_without_override_matches_plain_construction() -> None:
    config = IngestorConfig.load(postgres=_postgres())

    assert config.layers["parsed"] == "data/parsed"
    assert config.sources["cds"].file == "codice_della_strada.json"


def test_load_with_override_merges_over_the_base_yaml(tmp_path: Path) -> None:
    override_yaml = tmp_path / "ingestor_config.test-data.yaml"
    override_yaml.write_text(
        "layers:\n"
        "  parsed: data/test-data/parsed\n"
        "  cleaned: data/test-data/cleaned\n"
        "  enriched: data/test-data/enriched\n"
        "quiz_images_dir: data/test-data/quiz-images\n",
        encoding="utf-8",
    )

    config = IngestorConfig.load(override_yaml, postgres=_postgres())

    assert config.layers == {
        "parsed": "data/test-data/parsed",
        "cleaned": "data/test-data/cleaned",
        "enriched": "data/test-data/enriched",
    }
    assert config.quiz_images_dir == Path("data/test-data/quiz-images")
    # Fields the override file doesn't mention still come from the base yaml.
    assert config.sources["cds"].file == "codice_della_strada.json"
    assert config.rca_ranges == ["118-165", "278-300"]


def test_load_init_kwargs_win_over_the_override_file(tmp_path: Path) -> None:
    override_yaml = tmp_path / "ingestor_config.test-data.yaml"
    override_yaml.write_text("embed_repealed: true\n", encoding="utf-8")

    config = IngestorConfig.load(override_yaml, postgres=_postgres(), embed_repealed=False)

    assert config.embed_repealed is False


def test_load_does_not_mutate_the_base_ingestor_config_class(tmp_path: Path) -> None:
    override_yaml = tmp_path / "ingestor_config.test-data.yaml"
    override_yaml.write_text("embed_repealed: true\n", encoding="utf-8")

    IngestorConfig.load(override_yaml, postgres=_postgres())

    assert IngestorConfig._config_override_file is None
