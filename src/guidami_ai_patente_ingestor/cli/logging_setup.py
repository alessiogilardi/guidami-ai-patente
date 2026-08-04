"""Root logging configuration: console output plus a per-run log file under `logs/`."""

import logging
from pathlib import Path

from commons.observability import LOG_FORMAT, RunArtifactWriter


def configure_logging(
    project_root: Path, command: str, dry_run: bool, use_console_handler: bool = True
) -> Path | None:
    """Configures the root logger with a console handler, plus a file handler unless `dry_run`.

    `--dry-run` commands are advertised as making no filesystem writes (see
    `render_dry_run`); logging to `logs/` would break that contract, so dry runs log to
    console only.

    The caller passes `use_console_handler=False` when a `LiveDashboard` owns the
    console instead (its own `LogPanelHandler` is attached/detached by the dashboard's
    `__enter__`/`__exit__`, not here): in that case the run log file is the only sink
    this function installs.

    Returns the log file path, or None when `dry_run` is True.
    """
    handlers: list[logging.Handler] = []
    if use_console_handler:
        handlers.append(logging.StreamHandler())
    log_file: Path | None = None
    if not dry_run:
        run_dir = RunArtifactWriter.build_run_dir(project_root / "logs", f"ingest_{command}")
        log_file = run_dir / "run.log"
        handlers.append(logging.FileHandler(log_file))

    # force=True: without it, basicConfig is a no-op whenever the root logger already
    # has a handler (e.g. pytest's own log-capture handler during the test session, or
    # a second invocation within the same process), silently skipping ours.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers, force=True)
    return log_file
