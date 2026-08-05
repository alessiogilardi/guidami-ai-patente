"""Base content model for every `manifest.json`/`report.md` a `RunArtifactWriter` writes."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class RunManifest(BaseModel):
    """Base for every `manifest.json`/`report.md` content model.

    Not frozen: `started_at` is set once at construction, but concrete subclasses
    accumulate state during the run (`record_skip`, `record_flow`, ...) and
    `RunArtifactWriter.__exit__` sets `ended_at` on any instance before writing.
    """

    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None

    def to_report_lines(self) -> list[str]:
        """Renders this manifest's `report.md` content. Every concrete subclass overrides this."""
        raise NotImplementedError
