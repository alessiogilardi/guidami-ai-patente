import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Matches the `NUMERIC(12, 6)` column type of `llm_call_logs.cost_usd`.
_QUANTIZE = Decimal("0.000001")


class LlmCostCalculator:
    """Computes the best-effort USD cost of an LLM call via litellm's bundled pricing map."""

    def cost_usd(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> Decimal | None:
        """Returns the call's cost in USD, or `None` when it cannot be determined.

        Args:
            model: Original, litellm-style model id (not the `:`-rewritten pydantic_ai
                variant), e.g. `"openrouter/anthropic/claude-3.5-sonnet"`.
            input_tokens: Prompt token count, or `None` (e.g. on the error path).
            output_tokens: Completion token count, or `None`.

        Returns:
            Cost quantized to `Decimal("0.000001")`, or `None` when either token count
            is missing or `model` is not in litellm's pricing map.
        """
        if input_tokens is None or output_tokens is None:
            return None

        import litellm

        try:
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens
            )
        except Exception:
            logger.info(f"no litellm pricing data for model '{model}'; cost_usd stays NULL")
            return None

        return Decimal(str(prompt_cost + completion_cost)).quantize(_QUANTIZE)
