"""Resolves pywire components through the container `main.py` binds to `bot_data`.

Mirrors the fallback FastAPI's own dependency chain already uses
(`guidami_ai_patente/api/dependencies/user_identity.py::_get_user_repository`:
`getattr(request.app.state, "pywire_container", None) or get_default_container()`):
prefer the container this process's own composition root bound, falling back to the
process-wide default only when none was bound (e.g. a handler resolved from a unit
test that never populates `bot_data`). `python-telegram-bot` has no `app.state` of
its own — `Application.bot_data` (a plain dict, shared for the process's whole
lifetime and exposed to every handler as `context.bot_data`) is its closest
equivalent, and is what `main.py::_run` binds this to (spec 0016).
"""

from pywire import Container, get_default_container
from telegram.ext import ContextTypes

BOT_DATA_CONTAINER_KEY = "pywire_container"


def resolve[T](context: ContextTypes.DEFAULT_TYPE, service_type: type[T]) -> T:
    """Resolves `service_type`, preferring the container bound in `bot_data`."""
    assert context.bot_data is not None
    bound_container: Container | None = context.bot_data.get(BOT_DATA_CONTAINER_KEY)
    return (bound_container or get_default_container()).resolve(service_type)
