from decimal import Decimal

from commons.ai.observability import LlmCostCalculator

# Known to litellm's bundled pricing map (verified manually against the installed version).
_KNOWN_MODEL = "openrouter/anthropic/claude-3.5-sonnet"
_UNKNOWN_MODEL = "openrouter/does-not-exist/definitely-not-a-real-model"


def test_known_model_returns_quantized_decimal() -> None:
    calculator = LlmCostCalculator()

    cost = calculator.cost_usd(_KNOWN_MODEL, 1000, 500)

    assert cost is not None
    assert isinstance(cost, Decimal)
    assert cost > 0
    exponent = cost.as_tuple().exponent
    assert isinstance(exponent, int)
    assert exponent >= -6


def test_unknown_model_returns_none() -> None:
    calculator = LlmCostCalculator()

    cost = calculator.cost_usd(_UNKNOWN_MODEL, 100, 50)

    assert cost is None


def test_missing_input_tokens_returns_none() -> None:
    calculator = LlmCostCalculator()

    assert calculator.cost_usd(_KNOWN_MODEL, None, 50) is None


def test_missing_output_tokens_returns_none() -> None:
    calculator = LlmCostCalculator()

    assert calculator.cost_usd(_KNOWN_MODEL, 50, None) is None
