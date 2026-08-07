"""Run manifest for `ingest index`."""

from typing import Literal

from pydantic import Field

from commons.observability import RunManifest


class IndexManifest(RunManifest):
    """Run manifest for `ingest index` (entity/source/flows run)."""

    entity: Literal["knowledge", "quiz"]
    source: str | None = None
    flows: list[str] = Field(default_factory=list)
    quiz_variant_omissions: dict[str, int] = Field(default_factory=dict)

    def record_flow(self, name: str) -> None:
        """Appends `name`, called at the same point `ProgressReporter.begin_flow` is."""
        self.flows.append(name)

    def record_quiz_variant_omissions(self, counts: dict[str, int]) -> None:
        """Records FR-2's per-variant omission counts, called once after quiz indexing."""
        self.quiz_variant_omissions = counts

    def to_report_lines(self) -> list[str]:
        """Renders the index report from this manifest's own fields."""
        lines = [
            f"# Index report — {self.entity}",
            "",
            f"- Entity: {self.entity}",
            f"- Source: {self.source or '—'}",
            f"- Flows run: {', '.join(self.flows) if self.flows else 'None'}",
            f"- Started: {self.started_at.isoformat()}",
            f"- Ended: {self.ended_at.isoformat() if self.ended_at else '—'}",
        ]
        if self.quiz_variant_omissions:
            lines.append(f"- Quiz variant omissions: {self.quiz_variant_omissions}")
        return lines
