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
