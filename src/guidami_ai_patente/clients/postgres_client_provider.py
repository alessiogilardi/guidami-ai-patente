"""Container-managed client for the shared pooled Postgres client."""

from pywire import Autowired, client, pre_destroy

from commons.clients import PostgresClient
from guidami_ai_patente.configs import AppConfig
from labeling.wiring import build_postgres_client


@client
class PostgresClientProvider:
    """Owns the one pooled `PostgresClient` every API repository reads through.

    `PostgresClient` belongs to `commons/` and is constructed manually by the
    ingestor and the batch harness, so it cannot carry a pywire decorator without
    pushing the container outside `src/guidami_ai_patente/` (ADR 0015). Conceptually
    this class is a provider under AD-16 (revised): it supplies the pooled client to
    every repository that reads through it, none of which knows how the pool was
    built. The object is built inside this class's own `__init__`, which pywire calls
    *after* it has set every `Autowired` field (ADR 0017), so `self.config` is already
    available here. Stays decorated `@client` rather than `@provider` (spec 0013,
    FR-2): it isn't moving out of `clients/`, and changing the decorator without
    moving the file would blur the distinction FR-2 draws rather than sharpen it.

    One client, therefore one pool, for the whole process — the pool's sizing comes
    from `AppConfig.postgres` (deployment capacity, never the judge's identity;
    AD-26).

    Releases the pool via pywire 0.6.0's `@pre_destroy` (spec 0013, FR-6): before this,
    the pool opened here was never closed — pywire had no teardown mechanism when spec
    0012 introduced this provider. `Container.close()`, called from the API's shutdown
    lifespan (`api/app.py::_lifespan`), now runs `close` on this instance.
    """

    config: Autowired[AppConfig]

    def __init__(self) -> None:
        """Opens the pooled client from the injected configuration."""
        self.client: PostgresClient = build_postgres_client(self.config.postgres)

    @pre_destroy
    def close(self) -> None:
        """Closes the pooled client. Called once by `Container.close()`."""
        self.client.close()
