"""Root logging configuration: console output plus a per-run log file under `logs/`."""

import logging
from datetime import datetime
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _build_run_dir(logs_root: Path, command: str) -> Path:
    """Creates and returns a unique `<logs_root>/ingest_<command>_<timestamp>` directory.

    Falls back to a numeric suffix (`_2`, `_3`, ...) on a same-minute collision, e.g. two
    runs of the same command started within the same minute.
    """
    base_name = f"ingest_{command}_{datetime.now().strftime('%Y%m%d%H%M')}"
    run_dir = logs_root / base_name
    suffix = 2
    while True:
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            run_dir = logs_root / f"{base_name}_{suffix}"
            suffix += 1
        else:
            return run_dir


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
        run_dir = _build_run_dir(project_root / "logs", command)
        log_file = run_dir / "run.log"
        handlers.append(logging.FileHandler(log_file))

    # force=True: without it, basicConfig is a no-op whenever the root logger already
    # has a handler (e.g. pytest's own log-capture handler during the test session, or
    # a second invocation within the same process), silently skipping ours.
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=handlers, force=True)
    return log_file
