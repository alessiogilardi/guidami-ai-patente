"""Health-check domain service."""

from pywire import Autowired, service

from guidami_ai_patente.repositories.dependency_version_repository import (
    DependencyVersionRepository,
)


@service
class HealthCheckService:
    """Reports service liveness and the resolved runtime dependency versions.

    Deliberately not a `UseCase` (spec 0013, FR-4): it exposes two independent,
    argument-less public operations (`check`, `pywire_version`), and forcing a
    no-op request DTO on either would add ceremony for no behavioral benefit.
    """

    repository: Autowired[DependencyVersionRepository]

    def check(self) -> str:
        """Returns the liveness status."""
        return "ok"

    def pywire_version(self) -> str:
        """Returns the installed pywire version, resolved through the DI container itself."""
        return self.repository.get_version("pywire")
