"""Health-check domain service."""

from pywire import Autowired, service

from guidami_ai_patente.repositories.dependency_version_repository import (
    DependencyVersionRepository,
)


@service
class HealthCheckService:
    """Reports service liveness and the resolved runtime dependency versions."""

    repository: Autowired[DependencyVersionRepository]

    def check(self) -> str:
        """Returns the liveness status."""
        return "ok"

    def pywire_version(self) -> str:
        """Returns the installed pywire version, resolved through the DI container itself."""
        return self.repository.get_version("pywire")
