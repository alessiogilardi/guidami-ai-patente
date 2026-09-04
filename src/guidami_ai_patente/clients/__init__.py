"""Thin adapters to a resource still owned by a pre-pywire package or a third party.

`PostgresClientProvider` wraps `commons.clients.PostgresClient`; its placement here is
temporary, pending `commons/` itself adopting pywire (spec 0013, Non-Goals). New API
code that builds a shared value the container cannot autowire directly belongs in
`guidami_ai_patente/providers/` instead — see that package's docstring for the
criterion (AD-16).
"""

from .postgres_client_provider import PostgresClientProvider

__all__ = ["PostgresClientProvider"]
