"""Run manifest for `ingest prepare`."""

from typing import Literal

from pydantic import Field

from commons.observability import RunManifest


class PrepareManifest(RunManifest):
    """Run manifest for `ingest prepare` (entity/source/force/flows run)."""

    entity: Literal["knowledge", "quiz"]
    source: str | None = None
    force: bool
    flows: list[str] = Field(default_factory=list)

    def record_flow(self, name: str) -> None:
        """Appends `name`, called at the same point `ProgressReporter.begin_flow` is."""
        self.flows.append(name)

    def to_report_lines(self) -> list[str]:
        """Renders the prepare report from this manifest's own fields."""
        return [
            f"# Prepare report — {self.entity}",
            "",
            f"- Entity: {self.entity}",
            f"- Source: {self.source or '—'}",
            f"- Force: {self.force}",
            f"- Flows run: {', '.join(self.flows) if self.flows else 'None'}",
            f"- Started: {self.started_at.isoformat()}",
            f"- Ended: {self.ended_at.isoformat() if self.ended_at else '—'}",
        ]
