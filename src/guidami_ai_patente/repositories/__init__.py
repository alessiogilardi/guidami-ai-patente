"""Data-access layer of the API.

Read repositories shared with the ingestor (e.g. corpus/quiz retrieval) live in
`commons/repositories/db/`; this package holds repositories specific to the API only.
"""

from .agent_config_repository import AgentConfigRepository
from .dependency_version_repository import DependencyVersionRepository
from .glossary_read_repository import GlossaryReadRepository
from .golden_set_read_repository import GoldenSetReadRepository
from .quiz_answer_repository import QuizAnswerRepository
from .quiz_image_repository import QuizImageRepository
from .quiz_question_repository import QuizQuestionRepository
from .user_repository import UserRepository

__all__ = [
    "AgentConfigRepository",
    "DependencyVersionRepository",
    "GlossaryReadRepository",
    "GoldenSetReadRepository",
    "QuizAnswerRepository",
    "QuizImageRepository",
    "QuizQuestionRepository",
    "UserRepository",
]
