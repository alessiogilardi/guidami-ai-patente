from decimal import Decimal
from typing import Protocol


class _CostCalculator(Protocol):
    """Structural contract for `QueuedLlmCallTracker`'s cost-calculator dependency.

    Private: not a cross-package port like `LlmCallTracker`. It exists only so
    `QueuedLlmCallTracker` depends on an abstraction rather than the concrete
    `LlmCostCalculator`, keeping it testable with duck-typed fakes.
    """

    def cost_usd(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> Decimal | None: ...
