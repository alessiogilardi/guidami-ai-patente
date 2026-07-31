"""Entry point: `ingest <command> <entity> [options]`."""

import argparse
import logging
from contextlib import ExitStack

from rich.console import Console

from commons.observability import NullProgressReporter, ProgressReporter
from guidami_ai_patente_ingestor.configs import IngestorConfig

from . import wiring
from .commands import index, prepare, reset, status
from .logging_setup import configure_logging
from .parser import build_parser
from .rendering.dashboard import LiveDashboard, LogPanelHandler

logger = logging.getLogger(__name__)

# Commands that run a `Flow` and are eligible for the live dashboard; `reset`/`status`
# execute no `Flow` and define neither `--dry-run` nor `--plain` (Non-Goals).
_MONITORED_COMMANDS = frozenset({"prepare", "index"})


def _build_dashboard(args: argparse.Namespace) -> LiveDashboard | None:
    """Returns a dashboard for an interactive, monitored, non-dry run; otherwise None."""
    if args.command not in _MONITORED_COMMANDS:
        return None
    if getattr(args, "dry_run", False):
        return None
    if getattr(args, "plain", False):
        return None
    console = Console()
    if not console.is_terminal:
        return None
    return LiveDashboard(console, LogPanelHandler())


def main() -> None:
    """Loads config, builds the parser, configures logging, and dispatches to the command."""
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    layer_resolver = wiring.build_layer_resolver(config)

    parser = build_parser(config)
    args = parser.parse_args()

    dashboard = _build_dashboard(args)
    log_file = configure_logging(
        config.project_root,
        args.command,
        dry_run=getattr(args, "dry_run", False),
        use_console_handler=dashboard is None,
    )
    if log_file is not None:
        logger.info("Logging to %s", log_file)

    progress: ProgressReporter = dashboard if dashboard is not None else NullProgressReporter()
    with ExitStack() as stack:
        if dashboard is not None:
            stack.enter_context(dashboard)
        match args.command:
            case "prepare":
                open_router_provider = wiring.build_open_router_provider(config)
                prepare.run_prepare(
                    config, layer_resolver, open_router_provider, args, progress=progress
                )
            case "index":
                index.run_index(config, layer_resolver, args, progress=progress)
            case "reset":
                reset.run_reset(config, args)
            case "status":
                status.run_status(config, layer_resolver, args)
