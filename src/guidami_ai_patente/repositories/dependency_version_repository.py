"""Repository exposing installed dependency versions."""

from importlib import metadata

from pywire import repository


@repository
class DependencyVersionRepository:
    """Reads installed package versions from environment metadata."""

    def get_version(self, package: str) -> str:
        """Returns the installed version of the given package.

        Args:
            package: Distribution name as registered with pip/uv.

        Returns:
            The installed version string.
        """
        return metadata.version(package)
