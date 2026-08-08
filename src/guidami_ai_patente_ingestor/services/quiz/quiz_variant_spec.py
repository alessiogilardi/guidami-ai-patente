from collections.abc import Callable
from dataclasses import dataclass

from commons.ai.embedding import OptionalTextComposer
from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel


def _dedup_by_number(item: EmbeddedQuizModel) -> str:
    """Default dedup key: every per-question variant is already distinct by number."""
    return item.number


@dataclass(frozen=True)
class QuizVariantSpec:
    """One quiz query representation: a name, its text composer, and its dedup key.

    A dataclass (not a NamedTuple) because it carries a Callable field (dedup_key) —
    justification required by .claude/rules/code-conventions.md for NamedTuple,
    satisfied here by using dataclass instead.
    """

    name: str
    text_composer: OptionalTextComposer[EmbeddedQuizModel]
    dedup_key: Callable[[EmbeddedQuizModel], str] = _dedup_by_number
