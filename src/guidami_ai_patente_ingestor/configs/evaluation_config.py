from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationConfig(BaseModel):
    """Run parameters for `ingest evaluate retrieval` (FR-1).

    Every field has a default so the harness runs with no configuration override;
    `ingest evaluate retrieval --seed`/`--baseline-repetitions` (T-11) layer a CLI
    override on top of these. No run parameter is hardcoded in the harness itself —
    seed, baseline repetition count, `k` values and reporting thresholds all live here.
    """

    model_config = ConfigDict(frozen=True)

    seed: int = 42
    baseline_repetitions: int = 3
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5, 10])
    keyword_df_cutoffs: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 5, 10, 20, 50, 100, 250, 500]
    )
    text_coverage_thresholds: list[float] = Field(default_factory=lambda: [0.01, 0.02, 0.05, 0.10])
    quiz_embedding_variant: str = "search_queries"
    output_dir: Path = Path("data/eval")

    @field_validator("baseline_repetitions")
    @classmethod
    def _validate_baseline_repetitions(cls, value: int) -> int:
        """Rejects a repetition count below 1: FR-3 needs at least one baseline pass."""
        if value < 1:
            raise ValueError(f"baseline_repetitions must be >= 1, got {value}")
        return value

    @field_validator("k_values")
    @classmethod
    def _validate_k_values(cls, value: list[int]) -> list[int]:
        """Rejects an empty k_values: FR-4 has no ranking depth to report otherwise."""
        if not value:
            raise ValueError("k_values must not be empty")
        return value
