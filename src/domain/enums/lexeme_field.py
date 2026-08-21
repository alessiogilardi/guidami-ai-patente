from enum import StrEnum, auto


class LexemeField(StrEnum):
    """The `QuizEvaluationRow` fields FR-4 sanctions as lexeme sources.

    These are the only fields the labeling lexeme-extraction strategy may draw from —
    the enum is deliberately narrower than "every text field of `QuizEvaluationRow`"
    (e.g. `number`, `image_filename` are excluded on purpose).

    Member names must stay equal (case-insensitively) to the corresponding
    `QuizEvaluationRow` attribute names: `StrEnum._generate_next_value_` derives each
    member's value from its name via `auto()`, so `TOPIC = auto()` carries the value
    `"topic"` and so on. `getattr(row, field.value)` relies on that structural
    agreement to resolve without a lookup table.
    """

    TOPIC = auto()
    TEXT = auto()
    IMAGE_DESCRIPTION = auto()
