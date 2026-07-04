"""Unit tests for commons.repositories.file_repository.

Covers BaseFileRepository behaviour (via concrete subclasses), JsonRepository,
and YamlRepository — including round-trips, error paths, and type-inference.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

from commons.repositories.file_repository import (
    JsonRepository,
    YamlRepository,
)

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class SampleModel(BaseModel):
    name: str
    value: int


@dataclass
class SampleDataclass:
    name: str
    value: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample() -> SampleModel:
    return SampleModel(name="test", value=42)


def _sample_dc() -> SampleDataclass:
    return SampleDataclass(name="test", value=42)


# ---------------------------------------------------------------------------
# JsonRepository — round-trip
# ---------------------------------------------------------------------------


class TestJsonRepositoryRoundTrip:
    def test_single_object_round_trip(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        item = _sample()
        repo.write(item, "item.json")
        loaded = repo.load("item.json")
        assert loaded == item

    def test_list_round_trip(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        items = [SampleModel(name="a", value=1), SampleModel(name="b", value=2)]
        repo.write(items, "items.json")
        loaded = repo.load("items.json")
        assert loaded == items

    def test_empty_list_round_trip(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        repo.write([], "empty.json")
        assert repo.load("empty.json") == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        nested = tmp_path / "a" / "b" / "c.json"
        repo.write([_sample()], nested)
        assert nested.exists()

    def test_preserves_utf8(self, tmp_path: Path) -> None:
        class UnicodeModel(BaseModel):
            text: str

        repo = JsonRepository(tmp_path, UnicodeModel)
        item = UnicodeModel(text="È obbligatorio indossare le cinture.")
        repo.write(item, "uni.json")
        raw = (tmp_path / "uni.json").read_text(encoding="utf-8")
        assert "È obbligatorio" in raw

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        with pytest.raises(FileNotFoundError, match="missing.json"):
            repo.load("missing.json")

    def test_absolute_path_bypasses_base_path(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path / "base", SampleModel)
        absolute = tmp_path / "elsewhere" / "data.json"
        absolute.parent.mkdir(parents=True)
        repo.write([_sample()], absolute)
        loaded = repo.load(absolute)
        assert loaded == [_sample()]


# ---------------------------------------------------------------------------
# YamlRepository — round-trip
# ---------------------------------------------------------------------------


class TestYamlRepositoryRoundTrip:
    def test_single_object_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(tmp_path, SampleModel)
        item = _sample()
        repo.write(item, "item.yaml")
        loaded = repo.load("item.yaml")
        assert loaded == item

    def test_list_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(tmp_path, SampleModel)
        items = [SampleModel(name="x", value=10), SampleModel(name="y", value=20)]
        repo.write(items, "items.yaml")
        loaded = repo.load("items.yaml")
        assert loaded == items

    def test_empty_list_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(tmp_path, SampleModel)
        repo.write([], "empty.yaml")
        assert repo.load("empty.yaml") == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        repo = YamlRepository(tmp_path, SampleModel)
        nested = tmp_path / "deep" / "nested.yaml"
        repo.write([_sample()], nested)
        assert nested.exists()

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        repo = YamlRepository(tmp_path, SampleModel)
        with pytest.raises(FileNotFoundError, match="missing.yaml"):
            repo.load("missing.yaml")


# ---------------------------------------------------------------------------
# BaseFileRepository — get_instance and type inference
# ---------------------------------------------------------------------------


class TestGetInstance:
    def test_get_instance_produces_working_repository(self, tmp_path: Path) -> None:
        repo = JsonRepository.get_instance(tmp_path, SampleModel)
        items = [_sample()]
        repo.write(items, "data.json")
        assert repo.load("data.json") == items

    def test_get_instance_yaml(self, tmp_path: Path) -> None:
        repo = YamlRepository.get_instance(tmp_path, SampleModel)
        items = [_sample()]
        repo.write(items, "data.yaml")
        assert repo.load("data.yaml") == items


class TestTypeInference:
    def test_infer_from_typed_subclass(self, tmp_path: Path) -> None:
        class TypedRepo(JsonRepository[SampleModel]):
            pass

        repo = TypedRepo(tmp_path)
        items = [_sample()]
        repo.write(items, "data.json")
        assert repo.load("data.json") == items

    def test_no_type_param_raises_type_error(self, tmp_path: Path) -> None:
        class UntypedRepo(JsonRepository):
            pass

        with pytest.raises(TypeError, match="Cannot infer model type"):
            UntypedRepo(tmp_path)


# ---------------------------------------------------------------------------
# BaseFileRepository — (de)serialization of supported types
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_pydantic_model_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        item = _sample()
        repo.write(item, "pydantic.json")
        assert repo.load("pydantic.json") == item

    def test_dataclass_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleDataclass)
        item = _sample_dc()
        repo.write(item, "dc.json")
        loaded = repo.load("dc.json")
        assert loaded == item

    def test_dict_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, dict)
        item = {"name": "test", "value": 42}
        repo.write(item, "d.json")
        assert repo.load("d.json") == item

    def test_unsupported_type_serialize_raises(self, tmp_path: Path) -> None:
        repo = JsonRepository(tmp_path, SampleModel)
        with pytest.raises(TypeError, match="Unsupported type for serialization"):
            repo._serialize_item(42)  # type: ignore[arg-type]

    def test_invalid_file_content_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('"just a string"', encoding="utf-8")
        repo = JsonRepository(tmp_path, SampleModel)
        with pytest.raises(ValueError, match="dict or a list"):
            repo.load("bad.json")
