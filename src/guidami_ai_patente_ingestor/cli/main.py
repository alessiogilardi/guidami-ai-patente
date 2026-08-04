"""Entry point: `ingest [--config PATH] <command> <entity> [options]`."""

import argparse
import logging
from contextlib import ExitStack
from pathlib import Path

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
# execute no `Flow` and define no `--plain` (Non-Goals).
_MONITORED_COMMANDS = frozenset({"prepare", "index"})


def _is_dry_run(args: argparse.Namespace) -> bool:
    """True when this invocation must make no filesystem/DB writes.

    For `prepare`/`index`, dry-run is opt-in via `--dry-run` (default: real run).
    `reset` inverts this: it previews by default and `--apply` opts into the real,
    destructive run — so its dry-run-ness is the negation of `args.apply`.
    """
    if args.command == "reset":
        return not args.apply
    return getattr(args, "dry_run", False)


def _parse_config_override(argv: list[str] | None = None) -> tuple[Path | None, list[str]]:
    """Pre-parses `--config` out of `argv`, before `IngestorConfig` is built.

    Needed because the command parser is config-driven (`build_parser(config)`),
    so the config override must be resolved before that parser even exists.
    Returns the override path (`None` if `--config` was not passed) and the
    remaining argv for the real parser to consume.
    """
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Alternate ingestor_config.yaml (e.g. a test-data profile).",
    )
    pre_args, remaining_argv = pre_parser.parse_known_args(argv)
    return pre_args.config, remaining_argv


def _build_dashboard(args: argparse.Namespace) -> LiveDashboard | None:
    """Returns a dashboard for an interactive, monitored, non-dry run; otherwise None."""
    if args.command not in _MONITORED_COMMANDS:
        return None
    if _is_dry_run(args):
        return None
    if getattr(args, "plain", False):
        return None
    console = Console()
    if not console.is_terminal:
        return None
    return LiveDashboard(console, LogPanelHandler())


def main() -> None:
    """Loads config, builds the parser, configures logging, and dispatches to the command."""
    config_override, remaining_argv = _parse_config_override()
    config = IngestorConfig.load(config_override)
    layer_resolver = wiring.build_layer_resolver(config)

    parser = build_parser(config)
    args = parser.parse_args(remaining_argv)

    dashboard = _build_dashboard(args)
    log_file = configure_logging(
        config.project_root,
        args.command,
        dry_run=_is_dry_run(args),
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
