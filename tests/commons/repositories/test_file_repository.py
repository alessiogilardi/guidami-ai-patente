"""Unit tests for commons.repositories.file_repository.

Covers BaseFileRepository behaviour (via concrete subclasses), JsonRepository,
and YamlRepository — including round-trips, error paths, and type-inference.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

from commons.clients.file_system import LocalFileSystemClient
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
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        item = _sample()
        repo.write_one(item, "item.json")
        loaded = repo.load_one("item.json")
        assert loaded == item

    def test_list_round_trip(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        items = [SampleModel(name="a", value=1), SampleModel(name="b", value=2)]
        repo.write_list(items, "items.json")
        loaded = repo.load_list("items.json")
        assert loaded == items

    def test_empty_list_round_trip(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        repo.write_list([], "empty.json")
        assert repo.load_list("empty.json") == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        nested = tmp_path / "a" / "b" / "c.json"
        repo.write_list([_sample()], nested)
        assert nested.exists()

    def test_preserves_utf8(self, tmp_path: Path) -> None:
        class UnicodeModel(BaseModel):
            text: str

        repo = JsonRepository(UnicodeModel, file_system_client=LocalFileSystemClient(tmp_path))
        item = UnicodeModel(text="È obbligatorio indossare le cinture.")
        repo.write_one(item, "uni.json")
        raw = (tmp_path / "uni.json").read_text(encoding="utf-8")
        assert "È obbligatorio" in raw

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(FileNotFoundError, match="missing.json"):
            repo.load_one("missing.json")

    def test_absolute_path_outside_base_raises_permission_error(self, tmp_path: Path) -> None:
        base = tmp_path / "base"
        base.mkdir()
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(base))
        outside = tmp_path / "elsewhere" / "data.json"
        outside.parent.mkdir(parents=True)

        with pytest.raises(PermissionError, match="[Tt]raversal"):
            repo.write_list([_sample()], outside)


# ---------------------------------------------------------------------------
# YamlRepository — round-trip
# ---------------------------------------------------------------------------


class TestYamlRepositoryRoundTrip:
    def test_single_object_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        item = _sample()
        repo.write_one(item, "item.yaml")
        loaded = repo.load_one("item.yaml")
        assert loaded == item

    def test_list_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        items = [SampleModel(name="x", value=10), SampleModel(name="y", value=20)]
        repo.write_list(items, "items.yaml")
        loaded = repo.load_list("items.yaml")
        assert loaded == items

    def test_empty_list_round_trip(self, tmp_path: Path) -> None:
        repo = YamlRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        repo.write_list([], "empty.yaml")
        assert repo.load_list("empty.yaml") == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        repo = YamlRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        nested = tmp_path / "deep" / "nested.yaml"
        repo.write_list([_sample()], nested)
        assert nested.exists()

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        repo = YamlRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(FileNotFoundError, match="missing.yaml"):
            repo.load_one("missing.yaml")


# ---------------------------------------------------------------------------
# BaseFileRepository — get_instance and type inference
# ---------------------------------------------------------------------------


class TestGetInstance:
    def test_get_instance_produces_working_repository(self, tmp_path: Path) -> None:
        repo = JsonRepository.get_instance(
            SampleModel, file_system_client=LocalFileSystemClient(tmp_path)
        )
        items = [_sample()]
        repo.write_list(items, "data.json")
        assert repo.load_list("data.json") == items

    def test_get_instance_yaml(self, tmp_path: Path) -> None:
        repo = YamlRepository.get_instance(
            SampleModel, file_system_client=LocalFileSystemClient(tmp_path)
        )
        items = [_sample()]
        repo.write_list(items, "data.yaml")
        assert repo.load_list("data.yaml") == items


class TestTypeInference:
    def test_infer_from_typed_subclass(self, tmp_path: Path) -> None:
        class TypedRepo(JsonRepository[SampleModel]):
            pass

        repo = TypedRepo(file_system_client=LocalFileSystemClient(tmp_path))
        items = [_sample()]
        repo.write_list(items, "data.json")
        assert repo.load_list("data.json") == items

    def test_no_type_param_raises_type_error(self, tmp_path: Path) -> None:
        class UntypedRepo(JsonRepository):
            pass

        with pytest.raises(TypeError, match="Cannot infer model type"):
            UntypedRepo(file_system_client=LocalFileSystemClient(tmp_path))


# ---------------------------------------------------------------------------
# BaseFileRepository — (de)serialization of supported types
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_pydantic_model_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        item = _sample()
        repo.write_one(item, "pydantic.json")
        assert repo.load_one("pydantic.json") == item

    def test_dataclass_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleDataclass, file_system_client=LocalFileSystemClient(tmp_path))
        item = _sample_dc()
        repo.write_one(item, "dc.json")
        loaded = repo.load_one("dc.json")
        assert loaded == item

    def test_dict_round_trip_via_json(self, tmp_path: Path) -> None:
        repo = JsonRepository(dict, file_system_client=LocalFileSystemClient(tmp_path))
        item = {"name": "test", "value": 42}
        repo.write_one(item, "d.json")
        assert repo.load_one("d.json") == item

    def test_dict_list_round_trip_via_json(self, tmp_path: Path) -> None:
        """Round-trip a list of dict-typed models.

        Covers the case the removed isinstance blacklist used to special-case, where
        the model type itself is a dict and had to be told apart from a sequence.
        """
        repo = JsonRepository(dict, file_system_client=LocalFileSystemClient(tmp_path))
        items = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        repo.write_list(items, "d_list.json")
        assert repo.load_list("d_list.json") == items

    def test_unsupported_type_serialize_raises(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(TypeError, match="Unsupported type for serialization"):
            repo._serialize_item(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BaseFileRepository — shape validation (load_one / load_list)
# ---------------------------------------------------------------------------


class TestShapeValidation:
    def test_load_one_on_array_file_raises_value_error(self, tmp_path: Path) -> None:
        array_file = tmp_path / "array.json"
        array_file.write_text('[{"name": "a", "value": 1}]', encoding="utf-8")
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(ValueError, match="Expected a single object"):
            repo.load_one("array.json")

    def test_load_list_on_single_object_file_raises_value_error(self, tmp_path: Path) -> None:
        object_file = tmp_path / "object.json"
        object_file.write_text('{"name": "a", "value": 1}', encoding="utf-8")
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(ValueError, match="Expected an array"):
            repo.load_list("object.json")

    def test_load_one_on_scalar_file_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('"just a string"', encoding="utf-8")
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(ValueError, match="Expected a single object"):
            repo.load_one("bad.json")

    def test_load_list_on_scalar_file_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('"just a string"', encoding="utf-8")
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        with pytest.raises(ValueError, match="Expected an array"):
            repo.load_list("bad.json")


# ---------------------------------------------------------------------------
# BaseFileRepository — load_dir(dir)
# ---------------------------------------------------------------------------


class TestLoadDir:
    def test_load_dir_roundtrip(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        (tmp_path / "dir").mkdir()
        repo.write_one(SampleModel(name="a", value=1), "dir/a.json")
        repo.write_one(SampleModel(name="b", value=2), "dir/b.json")

        loaded = repo.load_dir("dir")

        assert loaded == [SampleModel(name="a", value=1), SampleModel(name="b", value=2)]

    def test_load_dir_empty_dir(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        assert repo.load_dir("does_not_exist") == []

    def test_load_dir_rejects_array_file(self, tmp_path: Path) -> None:
        repo = JsonRepository(SampleModel, file_system_client=LocalFileSystemClient(tmp_path))
        (tmp_path / "dir").mkdir()
        monolith = tmp_path / "dir" / "monolith.json"
        monolith.write_text(
            '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]', encoding="utf-8"
        )

        with pytest.raises(ValueError, match="one object per file"):
            repo.load_dir("dir")
