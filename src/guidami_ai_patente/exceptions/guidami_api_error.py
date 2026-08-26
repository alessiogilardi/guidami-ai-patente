"""Base of every domain error the API maps to an HTTP status."""


class GuidamiApiError(Exception):
    """Root of the API's domain exception hierarchy.

    Exists so the global handler can register one mapping per concrete error while
    still having a single type to reason about — and so a new domain error is a
    subclass plus a handler entry, never a `try/except` inside a router.
    """
