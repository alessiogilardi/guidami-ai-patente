"""Shared per-run artifact writer: `run.log`, `manifest.json`, `report.md`."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from .models import RunManifest

RUN_DIR_DATETIME_FORMAT = "%Y%m%d%H%M"
RUN_DIR_NAME_TEMPLATE = "{prefix}_{datetime}"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# Force every log record's asctime onto UTC, matching the datetime.now(UTC) timestamps
# used everywhere else (manifest.json, DB TIMESTAMPTZ columns). Global logging.Formatter
# class attribute — the stdlib-documented way to do this — so it applies to every
# Formatter created anywhere in the process, including basicConfig's internal one in
# cli/logging_setup.py and scrapers/normattiva.py, both of which import LOG_FORMAT from
# this module (see ADR on UTC timestamp convention).
logging.Formatter.converter = time.gmtime


def _make_dir(logs_root: Path, base_name: str) -> Path:
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


class RunArtifactWriter:
    """Owns one `logs/<prefix>_<timestamp>/` run directory.

    Used as a context manager: `__enter__` installs a `FileHandler` for
    `run.log` on the root logger; `__exit__` always writes `manifest.json`
    and `report.md` before detaching the handler, whether the run finished
    cleanly or raised (never suppresses the exception).
    """

    def __init__(self, logs_root: Path, run_id_prefix: str, manifest: RunManifest) -> None:
        """Reserves the run directory and prepares (but does not attach) the file handler."""
        self._run_dir = self.build_run_dir(logs_root, run_id_prefix)
        self._manifest = manifest
        self._file_handler = logging.FileHandler(self.log_file)
        self._file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    @staticmethod
    def build_run_dir(logs_root: Path, prefix: str) -> Path:
        """Creates and returns a unique `<logs_root>/<prefix>_<timestamp>` directory.

        Falls back to a numeric suffix (`_2`, `_3`, ...) on a same-minute collision.
        """
        base_name = RUN_DIR_NAME_TEMPLATE.format(
            prefix=prefix, datetime=datetime.now(UTC).strftime(RUN_DIR_DATETIME_FORMAT)
        )
        return _make_dir(logs_root, base_name)

    @property
    def run_dir(self) -> Path:
        """The `<logs_root>/<prefix>_<timestamp>` directory owned by this run."""
        return self._run_dir

    @property
    def log_file(self) -> Path:
        """The `run.log` path inside `run_dir`."""
        return self._run_dir / "run.log"

    @property
    def manifest(self) -> RunManifest:
        """The manifest instance this writer finalizes on `__exit__`."""
        return self._manifest

    @property
    def manifest_file(self) -> Path:
        """The `manifest.json` path inside `run_dir`."""
        return self._run_dir / "manifest.json"

    @property
    def report_file(self) -> Path:
        """The `report.md` path inside `run_dir`."""
        return self._run_dir / "report.md"

    def __enter__(self) -> "RunArtifactWriter":
        """Attaches the `run.log` file handler to the root logger."""
        logging.getLogger().addHandler(self._file_handler)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Writes `manifest.json`/`report.md` and detaches the file handler; never suppresses."""
        self._manifest.ended_at = datetime.now(UTC)
        self._write_manifest()
        self._write_report()
        logging.getLogger().removeHandler(self._file_handler)
        self._file_handler.close()

    def _write_manifest(self) -> None:
        self.manifest_file.write_text(
            self._manifest.model_dump_json(exclude_none=True, indent=2), encoding="utf-8"
        )

    def _write_report(self) -> None:
        self.report_file.write_text("\n".join(self._manifest.to_report_lines()), encoding="utf-8")
