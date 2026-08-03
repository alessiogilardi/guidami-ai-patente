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


def test_load_yaml_overrides_returns_empty_dict_when_no_override() -> None:
    from guidami_ai_patente_ingestor.cli.main import _load_yaml_overrides

    assert _load_yaml_overrides(None) == {}


def test_load_yaml_overrides_parses_the_override_file(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.main import _load_yaml_overrides

    override_yaml = tmp_path / "ingestor_config.test-data.yaml"
    override_yaml.write_text(
        "layers:\n"
        "  parsed: data/test-data/parsed\n"
        "quiz_images_dir: data/test-data/parsed/quiz-patente-ab/images\n",
        encoding="utf-8",
    )

    overrides = _load_yaml_overrides(override_yaml)

    assert overrides == {
        "layers": {"parsed": "data/test-data/parsed"},
        "quiz_images_dir": "data/test-data/parsed/quiz-patente-ab/images",
    }


def test_load_yaml_overrides_returns_empty_dict_for_an_empty_file(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.main import _load_yaml_overrides

    override_yaml = tmp_path / "empty.yaml"
    override_yaml.write_text("", encoding="utf-8")

    assert _load_yaml_overrides(override_yaml) == {}
