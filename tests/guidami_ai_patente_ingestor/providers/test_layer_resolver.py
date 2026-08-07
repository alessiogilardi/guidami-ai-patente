from pathlib import Path

import pytest

from guidami_ai_patente_ingestor.configs import SourceConfig
from guidami_ai_patente_ingestor.providers import LayerResolverProvider


def _resolver() -> LayerResolverProvider:
    layers = {
        "parsed": "data/parsed",
        "cleaned": "data/cleaned",
        "enriched": "data/enriched",
    }
    sources = {
        "cds": SourceConfig(dir="cds", file="codice_della_strada.json"),
        "cap": SourceConfig(dir="cap", file="codice_rca.json"),
        "quiz": SourceConfig(dir="quiz-patente-ab", file="quiz-patente-ab.json"),
    }
    return LayerResolverProvider(layers=layers, sources=sources)


def test_path_resolves_layer_and_source_correctly() -> None:
    resolver = _resolver()
    result = resolver.path("parsed", "cds")
    assert result == Path("data/parsed/cds/codice_della_strada.json")


def test_path_resolves_enriched_quiz_layer() -> None:
    resolver = _resolver()
    result = resolver.path("enriched", "quiz")
    assert result == Path("data/enriched/quiz-patente-ab/quiz-patente-ab.json")


def test_path_raises_for_unknown_layer() -> None:
    resolver = _resolver()
    with pytest.raises(KeyError, match="unknown_layer"):
        resolver.path("unknown_layer", "cds")


def test_path_raises_for_unknown_source() -> None:
    resolver = _resolver()
    with pytest.raises(KeyError, match="unknown_source"):
        resolver.path("parsed", "unknown_source")


def test_dir_returns_container() -> None:
    resolver = _resolver()
    result = resolver.dir("cleaned", "cds")
    assert result == Path("data/cleaned/cds")


def test_dir_unknown_layer_raises() -> None:
    resolver = _resolver()
    with pytest.raises(KeyError, match="unknown_layer"):
        resolver.dir("unknown_layer", "cds")


def test_dir_unknown_source_raises() -> None:
    resolver = _resolver()
    with pytest.raises(KeyError, match="unknown_source"):
        resolver.dir("cleaned", "unknown_source")
