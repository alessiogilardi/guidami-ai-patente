"""Step generico che applica una funzione di mapping a una lista di oggetti nel contesto."""

import logging
from collections.abc import Callable

from commons.flowstep import FlowContext, Step

logger = logging.getLogger(__name__)


class MapStep[T_In, T_Out](Step):
    """Applica una funzione di mapping 1:1 a ogni elemento di una lista nel contesto.

    Legge ``input_key``, applica ``mapper`` a ogni elemento e scrive il risultato
    in ``output_key``.  È un wrapper zero-boilerplate per tutti gli step del tipo
    "converti lista A → lista B".

    Args:
        name:       Nome univoco dello step nel flow.
        mapper:     Funzione pura ``In -> Out`` applicata a ogni elemento.
        input_key:  Chiave da cui leggere la lista sorgente nel ``FlowContext``.
        output_key: Chiave in cui scrivere la lista risultante nel ``FlowContext``.

    Example::

        step = MapStep(
            name="map_to_entity",
            mapper=QuizMapper.from_embeddable_to_quiz_question,
            input_key=context_keys.EMBEDDABLE_QUIZ,
            output_key=context_keys.QUIZ_ENTITIES,
        )
    """

    def __init__(
        self,
        name: str,
        mapper: Callable[[T_In], T_Out],
        input_key: str,
        output_key: str,
    ) -> None:
        """Inietta mapper, input key e output key."""
        super().__init__(name)
        self._mapper = mapper
        self._input_key = input_key
        self._output_key = output_key

    def execute(self, context: FlowContext) -> None:
        """Legge ``input_key``, mappa ogni elemento, scrive in ``output_key``.

        Args:
            context: Shared pipeline context.
        """
        items: list[T_In] = context.get(self._input_key)
        results: list[T_Out] = [self._mapper(item) for item in items]

        logger.info(
            "MapStep(%s): %d item(s) → %s",
            self._mapper.__qualname__,
            len(results),
            self._output_key,
        )

        context.put(self._output_key, results)

    def get_required_keys(self) -> set[str]:
        """Richiede ``input_key`` nel contesto."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produce ``output_key`` nel contesto."""
        return {self._output_key}
