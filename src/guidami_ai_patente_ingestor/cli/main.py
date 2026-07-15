"""Entry point: `ingest <command> <entity> [options]`."""

import logging

from guidami_ai_patente_ingestor.configs import IngestorConfig

from . import wiring
from .commands import index, prepare, reset, status
from .parser import build_parser


def main() -> None:
    """Loads logging + config, builds the parser, and dispatches to the matching command."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    layer_resolver = wiring.build_layer_resolver(config)

    parser = build_parser(config)
    args = parser.parse_args()

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
