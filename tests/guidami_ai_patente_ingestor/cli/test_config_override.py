from pathlib import Path


def test_config_override_absent_returns_none_and_full_argv() -> None:
    from guidami_ai_patente_ingestor.cli.main import _parse_config_override

    argv = ["prepare", "knowledge", "--source", "cds"]

    config_override, remaining_argv = _parse_config_override(argv)

    assert config_override is None
    assert remaining_argv == argv


def test_config_override_is_extracted_from_argv() -> None:
    from guidami_ai_patente_ingestor.cli.main import _parse_config_override

    argv = ["--config", "configs/ingestor_config.test-data.yaml", "prepare", "quiz"]

    config_override, remaining_argv = _parse_config_override(argv)

    assert config_override == Path("configs/ingestor_config.test-data.yaml")
    assert remaining_argv == ["prepare", "quiz"]


def test_config_override_works_after_the_subcommand() -> None:
    from guidami_ai_patente_ingestor.cli.main import _parse_config_override

    argv = ["index", "quiz", "--config", "configs/ingestor_config.test-data.yaml", "--dry-run"]

    config_override, remaining_argv = _parse_config_override(argv)

    assert config_override == Path("configs/ingestor_config.test-data.yaml")
    assert remaining_argv == ["index", "quiz", "--dry-run"]
