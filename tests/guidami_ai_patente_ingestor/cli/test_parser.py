from unittest.mock import MagicMock

import pytest


def _make_config_mock() -> MagicMock:
    """Return a minimal IngestorConfig mock with valid source catalogs."""
    config = MagicMock()
    config.knowledge_preparation.sources = ["cds", "cap"]
    config.knowledge_indexing.sources = ["cds", "cap"]
    config.quiz_preparation.sources = ["quiz"]
    config.quiz_indexing.sources = ["quiz"]
    return config


def test_required_source_exits() -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    with pytest.raises(SystemExit):
        parser.parse_args(["prepare", "knowledge"])


def test_help_lists_all_commands() -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    help_text = parser.format_help()

    for command in ("prepare", "index", "reset", "status"):
        assert command in help_text, f"expected {command!r} to be listed in --help output"


@pytest.mark.parametrize(
    "argv",
    [
        ["prepare", "knowledge", "--source", "cds", "--dry-run"],
        ["prepare", "quiz", "--dry-run"],
        ["index", "knowledge", "--source", "cds", "--dry-run"],
        ["index", "quiz", "--dry-run"],
    ],
)
def test_dry_run_flag_parses_true_on_every_command_entity(argv: list[str]) -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    args = parser.parse_args(argv)

    assert args.dry_run is True


def test_dry_run_flag_defaults_to_false() -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    args = parser.parse_args(["index", "quiz"])

    assert args.dry_run is False


@pytest.mark.parametrize("argv", [["reset", "knowledge"], ["reset", "quiz"]])
def test_reset_does_not_define_dry_run_flag(argv: list[str]) -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    with pytest.raises(SystemExit):
        parser.parse_args([*argv, "--dry-run"])


@pytest.mark.parametrize("argv", [["reset", "knowledge"], ["reset", "quiz"]])
def test_reset_apply_flag_defaults_to_false(argv: list[str]) -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    args = parser.parse_args(argv)

    assert args.apply is False


@pytest.mark.parametrize("argv", [["reset", "knowledge"], ["reset", "quiz"]])
def test_reset_apply_flag_parses_true(argv: list[str]) -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    args = parser.parse_args([*argv, "--apply"])

    assert args.apply is True


def test_plain_flag_only_on_monitored_commands() -> None:
    from guidami_ai_patente_ingestor.cli.parser import build_parser

    parser = build_parser(_make_config_mock())

    prepare_args = parser.parse_args(["prepare", "knowledge", "--source", "cds", "--plain"])
    index_args = parser.parse_args(["index", "quiz", "--plain"])
    index_default_args = parser.parse_args(["index", "quiz"])

    assert prepare_args.plain is True
    assert index_args.plain is True
    assert index_default_args.plain is False

    with pytest.raises(SystemExit):
        parser.parse_args(["reset", "knowledge", "--plain"])
    with pytest.raises(SystemExit):
        parser.parse_args(["status", "--plain"])
