"""Container-managed provider for the shared pooled Postgres client."""

from pywire import Autowired, client

from commons.clients import PostgresClient
from guidami_ai_patente.configs import AppConfig
from labeling.wiring import build_postgres_client


@client
class PostgresClientProvider:
    """Owns the one pooled `PostgresClient` every API repository reads through.

    `PostgresClient` belongs to `commons/` and is constructed manually by the
    ingestor and the batch harness, so it cannot carry a pywire decorator without
    pushing the container outside `src/guidami_ai_patente/` (ADR 0015). AD-16's rule
    for exactly that case is a provider: the shared object is built inside this
    class's own zero-argument `__init__`, which pywire calls *after* it has set every
    `Autowired` field (ADR 0017), so `self.config` is already available here.

    One provider, therefore one pool, for the whole process — the pool's sizing comes
    from `AppConfig.postgres` (deployment capacity, never the judge's identity;
    AD-26).
    """

    config: Autowired[AppConfig]

    def __init__(self) -> None:
        """Opens the pooled client from the injected configuration."""
        self.client: PostgresClient = build_postgres_client(self.config.postgres)
