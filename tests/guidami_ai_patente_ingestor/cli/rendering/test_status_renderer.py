from rich.console import Console

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente_ingestor.cli.models.status import (
    CommandReadiness,
    ReadinessState,
    SourceReadiness,
    StatusReport,
)
from guidami_ai_patente_ingestor.cli.rendering.status_renderer import render
from guidami_ai_patente_ingestor.configs import IngestorConfig

_PLAINTEXT_PASSWORD = "top-secret-db-password"
_PLAINTEXT_API_KEY = "sk-top-secret-api-key"


def _build_config() -> IngestorConfig:
    return IngestorConfig(
        postgres=PostgresConnectionConfig(
            host="localhost", user="guidami", password=_PLAINTEXT_PASSWORD, dbname="guidami"
        ),
        open_router_config={"api_key": _PLAINTEXT_API_KEY},  # type: ignore[arg-type]
    )


def test_renders_matrix_and_masks_secrets() -> None:
    """The rendered config/readiness output never contains plaintext secret values."""
    report = StatusReport(
        readiness=[
            CommandReadiness(
                command="prepare",
                entity="knowledge",
                sources=[SourceReadiness(source="cds", state=ReadinessState.RUNNABLE)],
            )
        ],
        tables=None,
        db_reachable=None,
    )
    console = Console(record=True, width=200)

    render(_build_config(), report, console)

    output = console.export_text()
    assert "prepare" in output
    assert "knowledge" in output
    assert _PLAINTEXT_PASSWORD not in output
    assert _PLAINTEXT_API_KEY not in output
