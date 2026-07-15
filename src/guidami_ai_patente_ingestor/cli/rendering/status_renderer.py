from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from guidami_ai_patente_ingestor.cli.models.status import StatusReport, TableHealth
from guidami_ai_patente_ingestor.configs import IngestorConfig


def render(config: IngestorConfig, report: StatusReport, console: Console) -> None:
    """Renders the config panel, the readiness matrix, and (if present) table health.

    Secrets (`postgres.password`, `open_router_config.api_key`) are never printed in
    clear: `_mask_secret` reduces them to `****`/`missing` before they reach `console`.
    """
    console.print(_config_panel(config))
    console.print(_readiness_table(report))
    if report.db_reachable is False:
        console.print("[bold red]Postgres unreachable[/bold red] -- table health unavailable.")
    if report.tables is not None:
        console.print(_health_table(report.tables))


def _config_panel(config: IngestorConfig) -> Panel:
    """Builds the config summary panel, masking secret values."""
    postgres_password = _mask_secret(config.postgres.password.get_secret_value())
    open_router_api_key = _mask_secret(config.open_router_config.api_key.get_secret_value())
    lines = [
        f"Postgres: {config.postgres.host}:{config.postgres.port}/{config.postgres.dbname} "
        f"(password: {postgres_password})",
        f"OpenRouter API key: {open_router_api_key}",
        f"Knowledge chunks table: {config.knowledge_chunks_table}",
        f"Quiz questions table: {config.quiz_questions_table}",
    ]
    return Panel("\n".join(lines), title="Configuration")


def _mask_secret(value: str) -> str:
    """Reduces a secret value to `missing` (empty) or `****` (set) -- never the value itself."""
    return "missing" if not value else "****"


def _readiness_table(report: StatusReport) -> Table:
    """Builds the (command x entity) readiness matrix: aggregate summary + per-source detail."""
    table = Table(title="Readiness")
    table.add_column("Command")
    table.add_column("Entity")
    table.add_column("Summary")
    table.add_column("Sources")
    for item in report.readiness:
        summary = ", ".join(f"{state.value}={count}" for state, count in item.summary.items())
        sources = ", ".join(f"{s.source}={s.state.value}" for s in item.sources)
        table.add_row(item.command, item.entity, summary, sources)
    return table


def _health_table(tables: list[TableHealth]) -> Table:
    """Builds the per-table existence + row-count health view."""
    table = Table(title="Table health")
    table.add_column("Table")
    table.add_column("Exists")
    table.add_column("Rows")
    for item in tables:
        rows = "-" if item.row_count is None else str(item.row_count)
        table.add_row(item.table, str(item.exists), rows)
    return table
