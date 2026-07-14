import dataclasses
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from string import Template
from typing import Any, cast

from pydantic import BaseModel
from pydantic_ai import BinaryContent

from commons.clients import FileReaderInterface

PromptInput = BaseModel | Mapping[str, Any] | str


class PromptRenderer:
    """Formats the user prompt template and attaches media."""

    def __init__(self, template_str: str, file_reader: FileReaderInterface | None = None) -> None:
        """Initialize the renderer with a `$var`-style template string.

        Args:
            template_str: User prompt template with `$var` placeholders.
            file_reader: Reader used to resolve `images` paths, relative to its
                base directory. Optional: only required when `render` is called
                with a non-empty `images` tuple.
        """
        self._template = Template(template_str)
        self._file_reader = file_reader

    def render(
        self, request: PromptInput, images: tuple[Path, ...] = ()
    ) -> str | list[str | BinaryContent]:
        """Substitute template variables and attach binary images.

        Args:
            request: Pydantic model, dataclass instance, `Mapping`, or
                pre-rendered `str` providing substitution values.
            images: Image paths, resolved relative to `file_reader`'s base
                directory, to attach as `BinaryContent`.

        Returns:
            Rendered string when no images are provided, otherwise a list
            containing the text followed by `BinaryContent` items.

        Raises:
            ValueError: If `images` is non-empty but no `file_reader` was
                configured.
            TypeError: If `request` is not a `BaseModel`, a dataclass instance,
                a `Mapping`, or a `str`.
        """
        variables = self._to_vars(request)
        # `_to_vars` returns `None` only when `request` is a pre-rendered `str`
        # that must bypass `Template.safe_substitute` and be used verbatim.
        text = (
            cast(str, request)
            if variables is None
            else self._template.safe_substitute(**variables)
        )

        if not images:
            return text

        if self._file_reader is None:
            raise ValueError("images were provided but no file_reader was configured")

        parts: list[str | BinaryContent] = [text]
        for img in images:
            mime_type, _ = mimetypes.guess_type(img)
            media_type = mime_type or "application/octet-stream"
            parts.append(
                BinaryContent(data=self._file_reader.read_bytes(img), media_type=media_type)
            )

        return parts

    @staticmethod
    def _to_vars(request: PromptInput) -> Mapping[str, Any] | None:
        """Dispatch `request` to a mapping of template substitution variables.

        Args:
            request: Pydantic model, dataclass instance, `Mapping`, or
                pre-rendered `str`.

        Returns:
            A mapping of substitution variables, or `None` when `request` is a
            `str` that must bypass template substitution.
        """
        if isinstance(request, BaseModel):
            return request.model_dump()
        if dataclasses.is_dataclass(request) and not isinstance(request, type):
            return dataclasses.asdict(cast(Any, request))
        if isinstance(request, Mapping):
            return request
        if isinstance(request, str):
            return None

        raise TypeError(f"Unsupported prompt request type: {type(request)!r}")
