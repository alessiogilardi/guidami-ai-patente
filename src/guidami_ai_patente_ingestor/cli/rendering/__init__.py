"""Rich-based presentation layer for the `ingest` CLI."""

from .dry_run_renderer import render_dry_run
from .status_renderer import render

__all__ = ["render", "render_dry_run"]
