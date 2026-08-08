"""Text composers: turn a model into the text sent for embedding.

Sixth embedding subpackage, alongside the five-responsibility shape
(`protocols/`, `services/`, `models/`, ...) documented in `docs/layout.md`:
`FieldSpecComposer`/`TemplateComposer` are neither services (no `UseCase`, no
I/O-bound domain logic) nor classic mappers (mappers in this repo are static,
not DI-injected, while these carry an injected configuration).
"""

from .callable_composer import CallableComposer
from .field_spec_composer import FieldSpecComposer
from .template_composer import TemplateComposer

__all__ = ["CallableComposer", "FieldSpecComposer", "TemplateComposer"]
