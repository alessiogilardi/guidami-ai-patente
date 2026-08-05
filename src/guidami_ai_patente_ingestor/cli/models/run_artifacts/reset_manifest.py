"""Run manifest for `ingest reset`."""

from typing import Literal

from commons.observability import RunManifest


class ResetManifest(RunManifest):
    """Run manifest for `ingest reset` (entity only — no flags, no flows)."""

    entity: Literal["knowledge", "quiz"]

    def to_report_lines(self) -> list[str]:
        """Renders the reset report from this manifest's own fields."""
        return [
            f"# Reset report — {self.entity}",
            "",
            f"- Entity: {self.entity}",
            f"- Started: {self.started_at.isoformat()}",
            f"- Ended: {self.ended_at.isoformat() if self.ended_at else '—'}",
        ]
