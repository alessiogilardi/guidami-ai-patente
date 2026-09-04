"""Reads quiz image bytes from the configured image directory."""

from pywire import Autowired, repository

from commons.clients.file_system import LocalFileSystemClient
from guidami_ai_patente.configs import AppConfig


@repository
class QuizImageRepository:
    """The image store, anchored to `quiz_images_dir` (FR-12).

    The anchoring is the point. `BaseFileSystemClient._resolve_path` joins the name to
    the base directory, resolves it, and raises `PermissionError` unless the result is
    still `is_relative_to` that directory — so no name, however malformed, can address a
    byte outside the image directory. The service above therefore needs no hand-rolled
    `Path(filename).name` check, and the one place that decides what "inside" means is
    this client rather than every caller.

    Missing files surface as `FileNotFoundError` from `_get_safe_read_path`; translating
    either failure into a 404 is the service's call, not this layer's.
    """

    config: Autowired[AppConfig]

    def __init__(self) -> None:
        """Anchors the file-system client to the configured image directory."""
        self._client = LocalFileSystemClient(self.config.quiz_images_dir)

    def read(self, filename: str) -> bytes:
        """Returns the file's bytes.

        Args:
            filename: Name of a file inside `quiz_images_dir`.

        Returns:
            The file's content.

        Raises:
            FileNotFoundError: No such file under `quiz_images_dir`.
            PermissionError: The name resolves outside `quiz_images_dir`.
        """
        return self._client.read_bytes(filename)
