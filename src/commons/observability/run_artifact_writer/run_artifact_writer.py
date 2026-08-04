"""Shared per-run artifact writer: `run.log`, `manifest.json`, `report.md`."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .run_artifact_writer_config import RunArtifactWriterConfig

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_SkipCategory = Literal["fetch_failed", "session_invalid", "parse_error"]
_REPORT_HEADINGS: dict[_SkipCategory, str] = {
    "fetch_failed": "Fetch failures",
    "session_invalid": "Session-invalid skips",
    "parse_error": "Parse errors",
}


class RunArtifactWriter:
    """Owns one `logs/<prefix>_<timestamp>/` run directory.

    Used as a context manager: `__enter__` installs a `FileHandler` for
    `run.log` on the root logger; `__exit__` always writes `manifest.json`
    and `report.md` before detaching the handler, whether the run finished
    cleanly or raised (never suppresses the exception).
    """

    def __init__(self, config: RunArtifactWriterConfig) -> None:
        """Reserves the run directory and prepares (but does not attach) the file handler."""
        self._run_dir = self.build_run_dir(config.logs_root, f"scrape_{config.source}")
        self._source = config.source
        self._toc_url = config.toc_url
        self._output_path = config.output_path
        self._started_at = datetime.now(UTC)
        self._found = 0
        self._saved = 0
        self._skips: dict[_SkipCategory, list[dict[str, str]]] = {
            "fetch_failed": [],
            "session_invalid": [],
            "parse_error": [],
        }
        self._file_handler = logging.FileHandler(self.log_file)
        self._file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    @staticmethod
    def build_run_dir(logs_root: Path, prefix: str) -> Path:
        """Creates and returns a unique `<logs_root>/<prefix>_<timestamp>` directory.

        Falls back to a numeric suffix (`_2`, `_3`, ...) on a same-minute collision.
        """
        base_name = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M')}"
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

    @property
    def run_dir(self) -> Path:
        """The `<logs_root>/<prefix>_<timestamp>` directory owned by this run."""
        return self._run_dir

    @property
    def log_file(self) -> Path:
        """The `run.log` path inside `run_dir`."""
        return self._run_dir / "run.log"

    def __enter__(self) -> "RunArtifactWriter":
        """Attaches the `run.log` file handler to the root logger."""
        logging.getLogger().addHandler(self._file_handler)
        return self

    def set_found(self, count: int) -> None:
        """Records the total number of items discovered for this run."""
        self._found = count

    def record_saved(self) -> None:
        """Increments the count of successfully saved items."""
        self._saved += 1

    def record_skip(self, category: _SkipCategory, article: str, detail: str) -> None:
        """Records a skip in `category`, with `article`'s label and a category-specific detail."""
        self._skips[category].append({"article": article, "detail": detail})

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Writes `manifest.json`/`report.md` and detaches the file handler; never suppresses."""
        self._write_manifest()
        self._write_report()
        logging.getLogger().removeHandler(self._file_handler)
        self._file_handler.close()

    def _write_manifest(self) -> None:
        manifest = {
            "source": self._source,
            "toc_url": self._toc_url,
            "output_path": str(self._output_path),
            "started_at": self._started_at.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "found": self._found,
            "saved": self._saved,
            "skipped": {category: len(entries) for category, entries in self._skips.items()},
        }
        (self._run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_report(self) -> None:
        lines = [f"# Scrape report — {self._source} — {self._run_dir.name}", ""]
        for category, heading in _REPORT_HEADINGS.items():
            lines.append(f"## {heading}")
            lines.append("")
            entries = self._skips[category]
            if entries:
                lines.extend(f"- {e['article']}: {e['detail']}" for e in entries)
            else:
                lines.append("None")
            lines.append("")
        (self._run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
