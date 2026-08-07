from pathlib import Path

import pytest
from pydantic import ValidationError

from guidami_ai_patente_ingestor.configs import EvaluationConfig


def test_defaults_present() -> None:
    config = EvaluationConfig()

    assert config.seed == 42
    assert config.baseline_repetitions == 3
    assert config.k_values == [1, 3, 5, 10]
    assert config.keyword_df_cutoffs == [1, 2, 3, 5, 10, 20, 50, 100, 250, 500]
    assert config.text_coverage_thresholds == [0.01, 0.02, 0.05, 0.10]
    assert config.quiz_embedding_variant == "search_queries"
    assert config.output_dir == Path("data/eval")
    assert config.rrf_k == 60


def test_config_is_frozen() -> None:
    config = EvaluationConfig()

    with pytest.raises(ValidationError):
        config.seed = 7


def test_zero_baseline_repetitions_raises_value_error() -> None:
    with pytest.raises(ValueError, match="0"):
        EvaluationConfig(baseline_repetitions=0)


def test_empty_k_values_raises_value_error() -> None:
    with pytest.raises(ValueError, match="k_values"):
        EvaluationConfig(k_values=[])
