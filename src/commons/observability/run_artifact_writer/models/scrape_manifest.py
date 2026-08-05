"""Run manifest for `scrapers/normattiva.py`."""

from pathlib import Path
from typing import Literal

from pydantic import PrivateAttr, computed_field

from .run_manifest import RunManifest

SkipCategory = Literal["fetch_failed", "session_invalid", "parse_error"]
_REPORT_HEADINGS: dict[SkipCategory, str] = {
    "fetch_failed": "Fetch failures",
    "session_invalid": "Session-invalid skips",
    "parse_error": "Parse errors",
}


class ScrapeManifest(RunManifest):
    """Run manifest for `scrapers/normattiva.py`.

    Fields: source/toc_url/output_path, found/saved/skipped.
    """

    source: str
    toc_url: str
    output_path: Path
    found: int = 0
    saved: int = 0

    _skips: dict[SkipCategory, list[dict[str, str]]] = PrivateAttr(
        default_factory=lambda: {"fetch_failed": [], "session_invalid": [], "parse_error": []}
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def skipped(self) -> dict[str, int]:
        """Per-category skip counts, serialized into `manifest.json` as `skipped`."""
        return {category: len(entries) for category, entries in self._skips.items()}

    def set_found(self, count: int) -> None:
        """Records the total number of items discovered for this run."""
        self.found = count

    def record_saved(self) -> None:
        """Increments the count of successfully saved items."""
        self.saved += 1

    def record_skip(self, category: SkipCategory, article: str, detail: str) -> None:
        """Records a skip in `category`, with `article`'s label and a category-specific detail."""
        self._skips[category].append({"article": article, "detail": detail})

    def to_report_lines(self) -> list[str]:
        """Renders the scrape report: one headed section per skip category (PD-5 on the title)."""
        run_label = f"scrape_{self.source}_{self.started_at.strftime('%Y%m%d%H%M')}"
        lines = [f"# Scrape report — {self.source} — {run_label}", ""]
        for category, heading in _REPORT_HEADINGS.items():
            lines.append(f"## {heading}")
            lines.append("")
            entries = self._skips[category]
            if entries:
                lines.extend(f"- {e['article']}: {e['detail']}" for e in entries)
            else:
                lines.append("None")
            lines.append("")
        return lines
