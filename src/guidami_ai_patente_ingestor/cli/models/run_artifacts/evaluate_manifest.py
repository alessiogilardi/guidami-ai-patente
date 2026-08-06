"""Run manifest for `ingest evaluate retrieval`."""

from typing import Literal

from commons.observability import RunManifest
from guidami_ai_patente_ingestor.configs import EvaluationConfig


class EvaluateManifest(RunManifest):
    """Run manifest for `ingest evaluate retrieval` (entity + run parameters).

    `parameters` starts at `EvaluationConfig()`'s bare defaults — `_build_manifest`
    (`logging_setup.py`) has no access to `IngestorConfig` at manifest-construction
    time, only to `args` — and is overwritten via `record_parameters` once
    `commands/evaluate.py` computes the actual config-plus-CLI-override values, before
    the run proceeds. `RunArtifactWriter.__exit__` only serialises the manifest at the
    very end of the run, so `manifest.json`/`report.md` always reflect the effective
    parameters, never the placeholder default.
    """

    entity: Literal["retrieval"]
    parameters: EvaluationConfig = EvaluationConfig()

    def record_parameters(self, parameters: EvaluationConfig) -> None:
        """Records the effective run parameters (config + CLI overrides), once known."""
        self.parameters = parameters

    def to_report_lines(self) -> list[str]:
        """Renders the evaluate report from this manifest's own fields."""
        return [
            f"# Evaluate report — {self.entity}",
            "",
            f"- Entity: {self.entity}",
            f"- Seed: {self.parameters.seed}",
            f"- Baseline repetitions: {self.parameters.baseline_repetitions}",
            f"- k values: {self.parameters.k_values}",
            f"- Quiz embedding variant: {self.parameters.quiz_embedding_variant}",
            f"- Started: {self.started_at.isoformat()}",
            f"- Ended: {self.ended_at.isoformat() if self.ended_at else '—'}",
        ]
