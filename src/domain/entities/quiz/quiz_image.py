from pydantic import BaseModel


class QuizImageEntity(BaseModel):
    """Row of the `quiz_images` table (see db/init.sql).

    `filename` is the table's own primary key (no BIGSERIAL id to omit).
    """

    filename: str
    description: str | None = None
