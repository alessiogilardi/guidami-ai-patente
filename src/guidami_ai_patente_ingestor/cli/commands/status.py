"""`ingest status [--online]` dispatch: filesystem readiness plus opt-in DB health."""

import argparse
import logging

import psycopg
from rich.console import Console

from guidami_ai_patente_ingestor.cli.models.status import StatusReport
from guidami_ai_patente_ingestor.cli.rendering import render
from guidami_ai_patente_ingestor.cli.services.status import StatusInspector, TableHealthChecker
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring

logger = logging.getLogger(__name__)


def run_status(
    config: IngestorConfig, layer_resolver: LayerResolver, args: argparse.Namespace
) -> None:
    """Build and render the status report. Never raises: online checks are best-effort."""
    readiness = StatusInspector(config, layer_resolver).evaluate_readiness()

    tables = None
    db_reachable: bool | None = None
    if args.online:
        try:
            postgres_client = wiring.build_postgres_client(config)
        except psycopg.Error:
            logger.warning("Postgres unreachable; status will not show table health")
            db_reachable = False
        else:
            with postgres_client:
                db_reachable = True
                repositories = wiring.build_health_repositories(config, postgres_client)
                tables = TableHealthChecker(repositories).check()

    report = StatusReport(readiness=readiness, tables=tables, db_reachable=db_reachable)
    render(config, report, Console())
