"""Root configuration for the FastAPI service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from commons.configs import PostgresConnectionConfig


class AppConfig(BaseSettings):
    """Root settings for the guidami-ai-patente API service.

    Built once at the entry point (`main.py`) and registered on the pywire container
    as a single instance — never loaded inside routers or services, and never built
    twice in one process: `register_instance` refuses to displace an existing
    registration, so a second instance either raises `RegistrationError` or is left
    unused while the container keeps serving the first. (It is *not* silently absorbed
    by a singleton cache: since pywire 0.6.0 `register()` does not modify the class it
    registers, so `AppConfig(...)` is an ordinary call returning a fresh object.)

    Declares no `labeling` field: `LabelingConfig` is a `BaseSettings` in its own
    right, loaded and registered independently by `main.py` (spec 0013, FR-1). A
    consumer that needs the shared labeling epoch declares its own
    `labeling_config: Autowired[LabelingConfig]` rather than reading
    `self.config.labeling`.
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
