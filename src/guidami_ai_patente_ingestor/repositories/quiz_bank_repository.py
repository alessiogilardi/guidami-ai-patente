import json
from pathlib import Path

from guidami_ai_patente_ingestor.entities import QuizMainQuestion


class QuizBankRepository:
    """Legge il quiz bank da file JSON."""

    def load(self, path: Path) -> list[QuizMainQuestion]:
        """Legge `path` e mappa ogni elemento in una `QuizMainQuestion`."""
        raw_questions = json.loads(path.read_text(encoding="utf-8"))
        return [QuizMainQuestion.model_validate(raw_question) for raw_question in raw_questions]
