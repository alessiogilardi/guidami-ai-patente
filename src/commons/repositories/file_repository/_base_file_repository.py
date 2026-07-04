from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel


class BaseFileRepository[T](ABC):
    """Base class for file-backed repositories.

    Handles Pydantic/dataclass (de)serialization and type inference.
    Concrete subclasses implement the format-specific read/write logic.
    """

    def __init__(self, base_path: str | Path, model_class: type[T] | None = None) -> None:
        self._base_path = Path(base_path).resolve()
        self._model_class = model_class or self._infer_model_class()

    @classmethod
    def get_instance(cls, base_path: str | Path, model_class: type[T]) -> "BaseFileRepository[T]":
        """Create an instance mapped to a model class without requiring a subclass."""
        return cls(base_path, model_class=model_class)

    def load(self, file_name: str | Path) -> T | Sequence[T]:
        """Load and deserialize objects from a file.

        Args:
            file_name: Path (relative to base_path) or absolute path to the file.

        Returns:
            A single deserialized object if the file contains a dict,
            or a list of objects if it contains an array.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file content is neither a dict nor a list.
        """
        raw_data = self._read_raw(self._resolve(file_name))

        match raw_data:
            case list():
                return [self._deserialize_item(item) for item in raw_data]
            case dict():
                return self._deserialize_item(raw_data)
            case _:
                raise ValueError("File content must be a dict or a list.")

    def write(self, data: T | Sequence[T], file_name: str | Path) -> None:
        """Serialize and write one object or a sequence to a file.

        Args:
            data: Single object or sequence of objects to serialize.
            file_name: Path (relative to base_path) or absolute path to the file.
        """
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, dict)):
            raw_data = [self._serialize_item(item) for item in data]
        else:
            raw_data = self._serialize_item(data)  # type: ignore

        self._write_raw(raw_data, self._resolve(file_name))

    @abstractmethod
    def _read_raw(self, path: Path) -> dict | list: ...

    @abstractmethod
    def _write_raw(self, data: dict | list, path: Path) -> None: ...

    def _resolve(self, path: str | Path) -> Path:
        return self._base_path / path

    def _infer_model_class(self) -> type[T]:
        """Infer the model type from the generic parameter declared on the subclass.

        Walks ``__orig_bases__`` looking for any parameterized ``BaseFileRepository``
        subclass and returns the first concrete (non-TypeVar) type argument.

        Raises:
            TypeError: If no concrete type argument can be found.
        """
        orig_bases = getattr(self.__class__, "__orig_bases__", tuple())
        for base in orig_bases:
            origin = getattr(base, "__origin__", None)
            if origin is None:
                continue
            try:
                is_repo_base = isinstance(origin, type) and issubclass(origin, BaseFileRepository)
            except TypeError:
                continue
            if is_repo_base:
                for arg in get_args(base):
                    if isinstance(arg, type):
                        return arg  # type: ignore[return-value]

        raise TypeError(
            f"Cannot infer model type for {self.__class__.__name__}. "
            "Either subclass with a type parameter (e.g. class Repo(JsonRepository[Model])) "
            "or instantiate via JsonRepository.get_instance(base_path, Model)."
        )

    def _deserialize_item(self, raw_item: dict[str, Any]) -> T:
        """Deserialize a raw dict into the target model type."""
        if issubclass(self._model_class, BaseModel):
            return self._model_class.model_validate(raw_item)
        if is_dataclass(self._model_class):
            return self._model_class(**raw_item)
        if issubclass(self._model_class, dict):
            return self._model_class(raw_item)  # type: ignore

        raise TypeError(f"Unsupported type for deserialization: {self._model_class}")

    def _serialize_item(self, item: T) -> dict[str, Any]:
        """Serialize a model instance to a plain dict."""
        if isinstance(item, BaseModel):
            return item.model_dump()
        if is_dataclass(item):
            return asdict(item)  # type: ignore
        if isinstance(item, dict):
            return item

        raise TypeError(f"Unsupported type for serialization: {type(item)}")
