from pydantic import BaseModel


class GlossaryEntryEntity(BaseModel):
    """Insertable projection of one `glossary_entries` row (see db/init.sql).

    `id`, `tsv_term` and `created_at` are DB-generated and have no field, per
    `.claude/rules/code-conventions.md`'s entity rules. `term_ru` is always `None` on
    the insert path this entity models (spec 0019 FR-6) — only
    `GlossaryTermUpdateRepository`'s separate `UPDATE` (FR-5/AD-11) ever writes a
    non-null value, never through this entity.

    `embedding` is deliberately generic, not `embedding_3_small`: which physical
    `embedding_*` column it lands in is `GlossaryConfig.embedding_column` (AD-4),
    resolved by `GlossaryEntryWriteRepository` at write time — this entity is
    package-internal (never shared with another package's own entity), so nothing
    else needs its field name to spell out a specific model.
    """

    source: str
    article_number: str
    comma_number: str
    term: str
    definition: str
    term_ru: str | None
    embedding: list[float]
