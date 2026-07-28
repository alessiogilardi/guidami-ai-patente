from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Self, get_args

from pydantic import BaseModel

from commons.clients.file_system import LocalFileSystemClient


class BaseFileRepository[T](ABC):
    """Base class for file-backed repositories.

    Handles Pydantic/dataclass (de)serialization and type inference.
    Concrete subclasses implement the format-specific read/write logic.
    """

    def __init__(
        self,
        model_class: type[T] | None = None,
        *,
        file_system_client: LocalFileSystemClient,
    ) -> None:
        self._file_system_client = file_system_client
        self._model_class = model_class or self._infer_model_class()

    @classmethod
    def get_instance(
        cls, model_class: type[T], *, file_system_client: LocalFileSystemClient
    ) -> Self:
        """Create an instance mapped to a model class without requiring a subclass."""
        return cls(model_class, file_system_client=file_system_client)

    def load(self, file_name: str | Path) -> T | Sequence[T]:
        """Load and deserialize objects from a file.

        Args:
            file_name: Path (relative to the file system client's base directory) or
                absolute path to the file.

        Returns:
            A single deserialized object if the file contains a dict,
            or a list of objects if it contains an array.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file content is neither a dict nor a list.
        """
        raw_data = self._read_raw(file_name)

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
            file_name: Path (relative to the file system client's base directory) or
                absolute path to the file.
        """
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, dict)):
            raw_data = [self._serialize_item(item) for item in data]
        else:
            raw_data = self._serialize_item(data)  # type: ignore

        self._write_raw(raw_data, file_name)

    def load_all(self, dir_path: str | Path) -> list[T]:
        """Load every file of a directory as ONE object each, ordered by filename.

        Args:
            dir_path: Directory holding one serialized object per file.

        Returns:
            Deserialized objects, in filename order (empty if the dir is absent).

        Raises:
            ValueError: If a file holds an array instead of a single object
                (typically a leftover monolithic artifact).
        """
        items: list[T] = []
        for file_path in self._file_system_client.list_files(dir_path):
            raw_data = self._read_raw(file_path)
            if not isinstance(raw_data, dict):
                raise ValueError(
                    f"Expected one object per file, found "
                    f"{type(raw_data).__name__} in '{file_path}'"
                )
            items.append(self._deserialize_item(raw_data))
        return items

    @abstractmethod
    def _read_raw(self, file_name: str | Path) -> dict | list: ...

    @abstractmethod
    def _write_raw(self, data: dict | list, file_name: str | Path) -> None: ...

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
            "or instantiate via JsonRepository.get_instance(Model, file_system_client)."
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
