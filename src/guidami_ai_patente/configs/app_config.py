"""Root configuration for the FastAPI service."""

from pathlib import Path

from pydantic import AliasChoices, Field
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
    agents_dir: Path = Field(
        validation_alias=AliasChoices("AGENTS_DIR", "agents_dir"),
        description=(
            "Directory holding the agent YAML files, for the API's own agents whose "
            "prompts enter no configuration epoch (today: explanation_writer.yaml). "
            "Declared separately from LabelingConfig.agents_dir, which resolves the "
            "epoch-controlled judge prompt, per ADR 0020's dual-directory shape; both "
            "alias AGENTS_DIR and are deliberately defaultless (AD-22)."
        ),
    )

    articles_table: str = "articles"
    article_commas_table: str = "article_commas"
    quiz_questions_table: str = "quiz_questions"
    quiz_question_embeddings_table: str = "quiz_question_embeddings"
    labeling_runs_table: str = "labeling_runs"
    quiz_labelings_table: str = "quiz_labelings"
    quiz_comma_labels_table: str = "quiz_comma_labels"
    quiz_images_table: str = "quiz_images"
    explanation_deadline_s: float = Field(
        default=25.0,
        gt=0.0,
        description=(
            "Wall-clock budget for one explanation request, judge and writer included "
            "(FR-13, D10). Deployment configuration, never judge identity: it is not on "
            "LabelingConfig and does not enter the epoch key. Enforced by "
            "ExplanationService rather than by lowering comma_labeler.yaml's own "
            "timeout, which the batch shares and needs longer."
        ),
    )
