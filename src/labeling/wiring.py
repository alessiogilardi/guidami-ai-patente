"""Manual DI builders for the shared labeling stack (spec 0012, AD-16, AD-27).

Parameterised on `LabelingConfig` and on individual values — never on a root settings
class — so both `IngestorConfig` (batch) and `AppConfig` (API) can drive them without
either package importing the other.
"""

from pathlib import Path

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import LlmCallLogRepository, LlmCallTracker, QueuedLlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.configs import PostgresConnectionConfig
from commons.repositories import YamlRepository
from commons.repositories.db import CorpusReadRepository, QuizReadRepository

from .agents import CommaLabelerAgent
from .configs import LabelingConfig
from .repositories import GoldenSetWriteRepository
from .services import CandidateSetService, QuestionLexemeService

_COMMA_LABELER_FILE = "comma_labeler.yaml"


def build_open_router_provider(api_key: str) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=api_key)


def build_postgres_client(config: PostgresConnectionConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config)


def build_tracker(postgres_client: PostgresClient) -> QueuedLlmCallTracker:
    """Builds the queued LLM call tracker, persisted through the given client."""
    return QueuedLlmCallTracker(LlmCallLogRepository(postgres_client))


def build_corpus_repository(
    articles_table: str, article_commas_table: str, postgres_client: PostgresClient
) -> CorpusReadRepository:
    """Builds the corpus read repository, given the ingestor's table names."""
    return CorpusReadRepository(articles_table, article_commas_table, postgres_client)


def build_quiz_repository(
    quiz_questions_table: str,
    quiz_question_embeddings_table: str,
    quiz_images_table: str,
    postgres_client: PostgresClient,
) -> QuizReadRepository:
    """Builds the quiz read repository, given the ingestor's table names."""
    return QuizReadRepository(
        quiz_questions_table,
        quiz_question_embeddings_table,
        quiz_images_table,
        postgres_client,
    )


def build_golden_set_repository(
    labeling_runs_table: str,
    quiz_labelings_table: str,
    quiz_comma_labels_table: str,
    postgres_client: PostgresClient,
) -> GoldenSetWriteRepository:
    """Builds the golden-set write repository, given the ingestor's table names."""
    return GoldenSetWriteRepository(
        labeling_runs_table,
        quiz_labelings_table,
        quiz_comma_labels_table,
        postgres_client,
    )


def build_comma_labeler_config(agents_dir: Path) -> AgentConfig:
    """Loads `comma_labeler.yaml` from `agents_dir`.

    The prompt text this returns is what `prompt_version` hashes, so the batch judge
    and the live judge agree only when both resolve the same `agents_dir` (AD-22).
    """
    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)
    )
    return agents_repository.load_one(_COMMA_LABELER_FILE)


def build_comma_labeler_agent(
    agent_config: AgentConfig,
    provider: OpenRouterProvider,
    tracker: LlmCallTracker | None = None,
) -> CommaLabelerAgent:
    """Builds the comma-labeler agent from an already-loaded `AgentConfig`.

    Takes the config already loaded (rather than calling `from_yaml`) so the caller
    loads the prompt exactly once and both hashes it into the epoch and builds the
    agent from it. `tracker` is optional: the API path runs without a
    `QueuedLlmCallTracker`, whose background lifecycle has no request-scoped owner.
    """
    return CommaLabelerAgent(config=agent_config, provider=provider, tracker=tracker)


def build_question_lexeme_service(
    config: LabelingConfig, corpus_repository: CorpusReadRepository
) -> QuestionLexemeService:
    """Builds the text arm's lexeme extractor from the configured lexeme fields."""
    return QuestionLexemeService(config.lexeme_fields, corpus_repository)


def build_candidate_set_service(
    config: LabelingConfig,
    corpus_repository: CorpusReadRepository,
    lexeme_service: QuestionLexemeService,
) -> CandidateSetService:
    """Builds the two-arm candidate union service at the configured arm depths."""
    return CandidateSetService(config.dense_k, config.text_k, corpus_repository, lexeme_service)
