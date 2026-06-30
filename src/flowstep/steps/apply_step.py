"""Step generico che applica una catena di transform (lista→lista) a un valore del contesto."""

import logging
from collections.abc import Callable
from typing import Any

from flowstep.core import FlowContext, Step

logger = logging.getLogger(__name__)


class ApplyStep(Step):
    """Applica in catena uno o più transform (lista→lista) a un valore del contesto.

    Args:
        name: Nome univoco dello step nel flow.
        transforms: Uno o più callable `list → list` applicati in sequenza.
        input_key: Chiave da cui leggere il valore sorgente nel `FlowContext`.
        output_key: Chiave in cui scrivere il risultato nel `FlowContext`.

    Example::

        step = ApplyStep(
            "clean",
            ForEach(ArticleCleaner()),
            input_key=context_keys.PARSED_ARTICLES,
            output_key=context_keys.CLEANED_ARTICLES,
        )
    """

    def __init__(
        self,
        name: str,
        *transforms: Callable[[list[Any]], list[Any]],
        input_key: str,
        output_key: str,
    ) -> None:
        """Inietta nome, catena di transform, input key e output key.

        Args:
            name: Nome univoco dello step.
            *transforms: Callable applicati in sequenza (zero o più).
            input_key: Chiave sorgente nel contesto.
            output_key: Chiave destinazione nel contesto.
        """
        super().__init__(name)
        self._transforms = transforms
        self._input_key = input_key
        self._output_key = output_key

    def execute(self, context: FlowContext) -> None:
        """Legge `input_key`, applica la catena di transform, scrive in `output_key`.

        Args:
            context: Shared pipeline context.
        """
        result: Any = context.get(self._input_key)
        for transform in self._transforms:
            result = transform(result)
        logger.info(
            "ApplyStep(%s): %d transform(s) → %s",
            self._name,
            len(self._transforms),
            self._output_key,
        )
        context.put(self._output_key, result)

    def get_required_keys(self) -> set[str]:
        """Richiede `input_key` nel contesto."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produce `output_key` nel contesto."""
        return {self._output_key}
