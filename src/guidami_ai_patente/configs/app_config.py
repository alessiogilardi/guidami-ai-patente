"""Root configuration for the FastAPI service."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from commons.configs import PostgresConnectionConfig
from labeling.configs import LabelingConfig


class AppConfig(BaseSettings):
    """Root settings for the guidami-ai-patente API service.

    Built once at the entry point (`main.py`) and registered on the pywire container
    as a single instance — never loaded inside routers or services, and never built
    twice in one process (a second instance would be silently ignored by the
    container's singleton cache).

    `labeling` is the shared `LabelingConfig`, resolved from the same
    `configs/labeling.yaml` and `AGENTS_DIR` the ingestor reads (spec 0012, AD-27).
    No epoch input may be declared here as a field of its own: the batch judge and
    the live judge agree about their identity only because there is one source.
    Pool sizing, by contrast, is deployment capacity and lives on
    `postgres` — never on `LabelingConfig`, which would put it in the epoch key
    (AD-26).
    """

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    postgres: PostgresConnectionConfig
    quiz_images_dir: Path = Path("data/quiz-images")

    articles_table: str = "articles"
    article_commas_table: str = "article_commas"
    quiz_questions_table: str = "quiz_questions"
    quiz_question_embeddings_table: str = "quiz_question_embeddings"
    labeling_runs_table: str = "labeling_runs"
    quiz_labelings_table: str = "quiz_labelings"
    quiz_comma_labels_table: str = "quiz_comma_labels"

    labeling: LabelingConfig = Field(default_factory=LabelingConfig)  # pyright: ignore[reportArgumentType]
