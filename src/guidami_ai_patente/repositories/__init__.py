"""Data-access layer of the API.

Read repositories shared with the ingestor (e.g. corpus/quiz retrieval) live in
`commons/repositories/db/`; this package holds repositories specific to the API only.
"""

from .agent_config_repository import AgentConfigRepository
from .dependency_version_repository import DependencyVersionRepository
from .quiz_question_repository import QuizQuestionRepository

__all__ = [
    "AgentConfigRepository",
    "DependencyVersionRepository",
    "QuizQuestionRepository",
]
