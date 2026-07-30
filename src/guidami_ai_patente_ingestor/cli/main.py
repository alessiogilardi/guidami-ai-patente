"""Entry point: `ingest <command> <entity> [options]`."""

import logging

from guidami_ai_patente_ingestor.configs import IngestorConfig

from . import wiring
from .commands import index, prepare, reset, status
from .logging_setup import configure_logging
from .parser import build_parser

logger = logging.getLogger(__name__)


def main() -> None:
    """Loads config, builds the parser, configures logging, and dispatches to the command."""
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    layer_resolver = wiring.build_layer_resolver(config)

    parser = build_parser(config)
    args = parser.parse_args()

    log_file = configure_logging(
        config.project_root, args.command, dry_run=getattr(args, "dry_run", False)
    )
    if log_file is not None:
        logger.info("Logging to %s", log_file)

    match args.command:
        case "prepare":
            open_router_provider = wiring.build_open_router_provider(config)
            prepare.run_prepare(config, layer_resolver, open_router_provider, args)
        case "index":
            index.run_index(config, layer_resolver, args)
        case "reset":
            reset.run_reset(config, args)
        case "status":
            status.run_status(config, layer_resolver, args)
